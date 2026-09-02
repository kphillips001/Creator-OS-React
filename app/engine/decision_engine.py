from datetime import datetime, timezone
import re

from app.services.situation_routing_service import SituationRoutingService
from app.services.silent_buyer_service import SilentBuyerService
from app.services.outreach_service import OutreachService
from app.services.hot_buyer_detection_service import HotBuyerDetectionService
from app.services.gpt_intent_classifier_service import GPTIntentClassifierService
from app.config import settings
from app.services.content_gating_service import ContentGatingService
from app.services.objection_classifier_service import ObjectionClassifierService
from app.services.response_behavior_service import ResponseBehaviorService
from app.services.ownership_decision_projection import OwnershipDecisionProjection
from app.services.content_usage_service import ContentUsageService
from app.services.decision_engine_runtime_boundary import (
    DecisionEngineRuntimeBoundary,
)
from app.services.product_recommendation_service import (
    ProductRecommendationService,
)
from app.models.content_recommendation import RecommendationRequest
from app.services.content_recommendation_service import (
    ContentRecommendationService,
)
from app.services.commerce_execution_policy import CommerceExecutionPolicy
from app.models.chat_commerce_delivery import ChatDeliveryRequest
from app.services.chat_commerce_delivery_service import ChatCommerceDeliveryService
from app.services.cms_contract_service import CMSContractService

from app.services.decision_engine_intimacy_integration_service import (
    DecisionEngineIntimacyIntegrationService,
)

from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)

from app.services.runtime_behavior_enforcement_service import (
    RuntimeBehaviorEnforcementService,
)

from app.services.runtime_suppression_enforcement_service import (
    RuntimeSuppressionEnforcementService,
)

from app.services.whale_retention_psychology_service import (
    WhaleRetentionPsychologyService,
)

from app.services.premium_relationship_memory_service import (
    PremiumRelationshipMemoryService,
)

from app.services.emotional_presence_refinement_service import (
    EmotionalPresenceRefinementService,
)

from app.services.premium_conversation_continuity_service import (
    PremiumConversationContinuityService,
)

from app.services.whale_burnout_prevention_service import (
    WhaleBurnoutPreventionService,
)

from app.services.emotional_dependency_classifier_service import (
    EmotionalDependencyClassifierService,
)

from app.services.long_term_emotional_stability_service import (
    LongTermEmotionalStabilityService,
)

from app.services.runtime_relationship_compatibility_service import (
    RuntimeRelationshipCompatibilityService,
)

from app.services.relationship_recovery_service import (
    RelationshipRecoveryService,
)

from app.services.advanced_intimacy_governance_service import (
    AdvancedIntimacyGovernanceService,
)

from app.services.final_relationship_intelligence_service import (
    FinalRelationshipIntelligenceService,
)
from app.models.runtime_decision import DecisionEngineResult

class DecisionEngine:
    @staticmethod
    def _canonical_attention_compatibility(projection: dict) -> dict:
        """Flatten the canonical per-turn projection for legacy GPT inputs."""
        canonical = dict(projection or {})
        compatibility = dict(canonical.get("compatibility") or {})
        compatibility.update({
            "attention_tier": str(
                canonical.get("attentionTier") or "MEDIUM"
            ).lower(),
            "effort_mode": str(
                canonical.get("effortMode") or "BALANCED"
            ).lower(),
            "user_value_tier": str(
                canonical.get("valueTier") or "STANDARD"
            ).lower(),
            "is_whale": canonical.get("valueTier") == "WHALE",
            "timewaster_flags": list(
                canonical.get("timeWasterEvidence") or ()
            ),
        })
        return compatibility

    def __init__(
        self,
        memory_service,
        intent_service,
        user_value_service,
        mode_engine,
        offer_service,
        content_service,
        post_offer_service,
        timing_engine,
        gpt_service,
        settings,
        logger,
        decision_runtime_boundary=None,
        content_usage_service=None,
    ):
        self.memory = memory_service
        self.intent = intent_service
        self.user_value = user_value_service
        self.mode = mode_engine
        self.offer = offer_service
        self.content = content_service
        self.post_offer = post_offer_service
        self.timing = timing_engine
        self.gpt = gpt_service
        self.settings = settings
        self.logger = logger
        self.situation_routing_service = SituationRoutingService()
        self.silent_buyer = SilentBuyerService()
        self.outreach_service = OutreachService()
        self.hot_buyer_service = HotBuyerDetectionService()
        self.gpt_intent_classifier = GPTIntentClassifierService(settings.OPENAI_API_KEY)
        self.content_gating_service = ContentGatingService()
        self.objection_classifier = ObjectionClassifierService()
        self.response_behavior_service = ResponseBehaviorService()
        self.ownership_decisions = OwnershipDecisionProjection()
        self.decision_runtime_boundary = (
            decision_runtime_boundary or DecisionEngineRuntimeBoundary()
        )
        self.content_usage_service = content_usage_service or ContentUsageService()
        self.intimacy_integration_service = (
            DecisionEngineIntimacyIntegrationService()
        )
        self.smooth_intimacy_escalation_service = (
            SmoothIntimacyEscalationService()
        )

        self.runtime_behavior_enforcement_service = (
            RuntimeBehaviorEnforcementService()
        )

        self.runtime_suppression_enforcement_service = (
            RuntimeSuppressionEnforcementService()
        )

        self.whale_retention_psychology_service = (
            WhaleRetentionPsychologyService()
        )

        self.premium_relationship_memory_service = (
            PremiumRelationshipMemoryService()
        )

        self.emotional_presence_refinement_service = (
            EmotionalPresenceRefinementService()
        )

        self.premium_conversation_continuity_service = (
            PremiumConversationContinuityService()
        )

        self.whale_burnout_prevention_service = (
            WhaleBurnoutPreventionService()
        )

        self.emotional_dependency_classifier = (
            EmotionalDependencyClassifierService(
                api_key=settings.OPENAI_API_KEY
            )
        )
        self.long_term_emotional_stability_service = (
            LongTermEmotionalStabilityService()
        )

        self.runtime_relationship_compatibility_service = (
            RuntimeRelationshipCompatibilityService()
        )

        self.relationship_recovery_service = (
            RelationshipRecoveryService()
        )

        self.advanced_intimacy_governance_service = (
            AdvancedIntimacyGovernanceService()
        )

        self.final_relationship_intelligence_service = (
            FinalRelationshipIntelligenceService()
        )
        self.product_recommendation_service = ProductRecommendationService(
            content_service=self.content,
            logger=self.logger,
        )
        try:
            from app.services.chat_commerce_registration_service import (
                ChatCommerceRegistrationService,
            )

            self.chat_commerce_inventory_service = ChatCommerceRegistrationService()
        except Exception:
            self.chat_commerce_inventory_service = None
        self.content_recommendation_service = ContentRecommendationService(
            chat_commerce_inventory_service=self.chat_commerce_inventory_service,
            logger=self.logger,
        )
        self.chat_commerce_delivery_service = ChatCommerceDeliveryService(
            chat_commerce_registration_service=self.chat_commerce_inventory_service,
        )
        self.cms_contract_service = CMSContractService()
        self.last_cms_offer_candidate_contract = None
        self.last_cms_customer_progress_contract = None

    def _select_cms_content(
        self,
        offer_type: str,
        working_memory: dict,
    ) -> dict | None:
        """
        CMS-only content selector.

        All DecisionEngine content selection MUST pass through
        ContentService.get_content().
        """

        normalized_offer_type = offer_type or "none"

        if normalized_offer_type.endswith("_offer"):
            normalized_offer_type = normalized_offer_type.replace("_offer", "")

        if normalized_offer_type in ["none", None]:
            self.logger.info("[CMS CONTENT SELECT] skipped: offer_type=none")
            return None

        chat_inventory_payload = self._select_chat_commerce_inventory_content(
            normalized_offer_type,
            working_memory,
        )
        if chat_inventory_payload is not None:
            self.logger.info(
                "[CMS CONTENT SELECT] source=ChatCommerceInventory | "
                f"type={normalized_offer_type} | persona={self.settings.DEFAULT_PERSONA}"
            )
            self.last_cms_offer_candidate_contract = None
            self.last_cms_customer_progress_contract = (
                self.cms_contract_service.build_customer_progress(
                    self._cms_customer_id(working_memory),
                    user_memory=working_memory,
                )
            )
            return chat_inventory_payload

        self.logger.info(
            f"[CMS CONTENT SELECT] source=ProductRecommendationService | "
            f"fallback=ContentService.get_content | "
            f"type={normalized_offer_type} | persona={self.settings.DEFAULT_PERSONA}"
        )

        selected_content = self.product_recommendation_service.get_content(
            normalized_offer_type,
            self.settings.DEFAULT_PERSONA,
            working_memory,
        )
        self.last_cms_offer_candidate_contract = (
            self.product_recommendation_service.last_offer_candidate_contract
        )
        self.last_cms_customer_progress_contract = (
            self.cms_contract_service.build_customer_progress(
                self._cms_customer_id(working_memory),
                user_memory=working_memory,
            )
        )
        return selected_content

    def _select_chat_commerce_inventory_content(
        self,
        offer_type: str,
        working_memory: dict,
    ) -> dict | None:
        creator_profile_id = (
            working_memory.get("creator_profile_id")
            or working_memory.get("active_creator_profile_id")
        )
        try:
            creator_profile_id = (
                int(creator_profile_id) if creator_profile_id is not None else None
            )
        except (TypeError, ValueError):
            creator_profile_id = None
        recommendation_service = getattr(
            self,
            "content_recommendation_service",
            None,
        )
        if recommendation_service is not None:
            try:
                result = recommendation_service.recommend(
                    RecommendationRequest(
                        creator_profile_id=creator_profile_id,
                        customer_context=working_memory,
                        conversation_context={
                            "last_user_message": working_memory.get(
                                "last_user_message"
                            ),
                            "intent_signals": working_memory.get(
                                "intent_signals",
                                (),
                            ),
                        },
                        decision_context=working_memory,
                        offer_type=offer_type,
                        persona=self.settings.DEFAULT_PERSONA,
                        limit=1,
                        candidate_limit=25,
                    )
                )
                candidate = result.top_candidate
                if candidate is not None:
                    payload = candidate.to_legacy_payload(
                        self.settings.DEFAULT_PERSONA,
                        offer_type,
                    )
                    return self._prepare_chat_commerce_delivery_payload(
                        payload,
                        recommendation=candidate.to_context(),
                        working_memory=working_memory,
                        offer_type=offer_type,
                    )
            except Exception as error:
                self.logger.info(
                    "[CONTENT RECOMMENDATION FALLBACK] "
                    f"reason={type(error).__name__}"
                )

        service = getattr(self, "chat_commerce_inventory_service", None)
        if service is None:
            return None
        try:
            candidates = service.get_recommendation_candidates(
                creator_profile_id=creator_profile_id,
                limit=25,
            )
        except Exception:
            return None
        for candidate in candidates:
            eligibility = service.eligibility_for_asset(
                candidate.asset_id,
                customer_context=working_memory,
            )
            if candidate.metadata.get("item_kind") == "photoshoot" or eligibility.recommendation_eligible:
                payload = candidate.to_legacy_payload(
                    self.settings.DEFAULT_PERSONA,
                    offer_type,
                )
                return self._prepare_chat_commerce_delivery_payload(
                    payload,
                    recommendation=payload,
                    working_memory=working_memory,
                    offer_type=offer_type,
                )
        return None

    def _prepare_chat_commerce_delivery_payload(
        self,
        payload: dict,
        *,
        recommendation,
        working_memory: dict,
        offer_type: str,
    ) -> dict:
        service = getattr(self, "chat_commerce_delivery_service", None)
        if service is None:
            return payload
        asset_id = payload.get("asset_id") or payload.get("content_item_id")
        if asset_id is None:
            return payload
        try:
            recommendation_metadata = payload.get("recommendation_metadata")
            if not isinstance(recommendation_metadata, dict):
                recommendation_metadata = {}
            result = service.prepare_delivery(
                ChatDeliveryRequest(
                    asset_id=int(asset_id),
                    recommendation=recommendation,
                    recommendation_id=(
                        payload.get("recommendation_id")
                        or recommendation_metadata.get("recommendation_id")
                    ),
                    customer_context=working_memory or {},
                    conversation_context={
                        "conversation_id": (working_memory or {}).get(
                            "conversation_id"
                        ),
                        "last_user_message": (working_memory or {}).get(
                            "last_user_message"
                        ),
                        "intent_signals": (working_memory or {}).get(
                            "intent_signals",
                            (),
                        ),
                    },
                    decision_context={
                        **dict(working_memory or {}),
                        "offer_type": offer_type,
                        "persona": self.settings.DEFAULT_PERSONA,
                    },
                    provider="telegram",
                    customer_id=str(
                        (working_memory or {}).get("customer_id")
                        or (working_memory or {}).get("user_id")
                        or (working_memory or {}).get("fanvue_user_id")
                        or ""
                    )
                    or None,
                    conversation_id=(working_memory or {}).get("conversation_id"),
                    metadata={"source": "DecisionEngine"},
                )
            )
        except Exception as error:
            self.logger.info(
                "[CHAT COMMERCE DELIVERY FALLBACK] "
                f"reason={type(error).__name__}"
            )
            return payload

        context = result.to_context()
        delivery_payload = context.get("payload") or {}
        payload["chat_delivery_result"] = context
        payload["chat_delivery_payload"] = delivery_payload
        payload["delivery_prepared"] = bool(result.success)
        payload["delivery_allowed"] = bool(result.success)
        payload["delivery_validation_failures"] = (
            context.get("validation", {}).get("failures", [])
        )
        payload["delivery_blocking_reason"] = result.failure_reason
        if delivery_payload:
            payload["delivery_id"] = delivery_payload.get("delivery_id")
            payload["recommendation_id"] = delivery_payload.get("recommendation_id")
            payload["fulfillment_id"] = delivery_payload.get("fulfillment_id")
            payload["provider_media_id"] = delivery_payload.get("provider_media_id")
            payload["media_link"] = delivery_payload.get("media_link")
            payload["fanvue_link"] = delivery_payload.get("media_link")
            payload["checkout_url"] = delivery_payload.get("media_link")
            payload["product_id"] = payload.get("product_id") or delivery_payload.get(
                "product_id"
            )
            payload["experience_id"] = payload.get("experience_id") or (
                delivery_payload.get("experience_id")
            )
            payload["delivery_type"] = delivery_payload.get("delivery_type")
            payload["delivery_permission_mode"] = (
                "paid"
                if delivery_payload.get("delivery_method") == "paid_media_link"
                else "free"
            )
            payload["delivery_requires_payment"] = (
                delivery_payload.get("delivery_method") == "paid_media_link"
            )
        return payload

    def _cms_customer_id(self, working_memory: dict | None) -> str:
        working_memory = working_memory or {}
        return str(
            working_memory.get("customer_id")
            or working_memory.get("user_id")
            or working_memory.get("fanvue_user_id")
            or "unknown"
        )

    def _cms_offer_candidate(self, selected_content=None):
        contract = getattr(self, "last_cms_offer_candidate_contract", None)
        if contract is not None:
            return contract
        return None

    def _cms_content_product_id(self, selected_content: dict | None):
        contract = self._cms_offer_candidate(selected_content)
        if contract and contract.product:
            return contract.product.product_id
        if not selected_content:
            return None
        return selected_content.get("product_id")

    def _cms_content_tag(self, selected_content: dict | None):
        product_id = self._cms_content_product_id(selected_content)
        if product_id:
            return f"product_{product_id}"
        if not selected_content:
            return None
        return selected_content.get("tag") or selected_content.get("id")

    def _cms_content_item_id(self, selected_content: dict | None):
        contract = self._cms_offer_candidate(selected_content)
        if contract and contract.product:
            return None
        if not selected_content:
            return None
        return selected_content.get("id") or selected_content.get("content_item_id")

    def _cms_content_offer_type(
        self,
        selected_content: dict | None,
        fallback: str | None = None,
    ):
        contract = self._cms_offer_candidate(selected_content)
        if contract:
            return contract.offer_kind.value
        if not selected_content:
            return fallback
        return selected_content.get("type") or fallback

    def _cms_content_price(self, selected_content: dict | None):
        contract = self._cms_offer_candidate(selected_content)
        if contract:
            return self._cms_price_from_cents(contract.price_cents)
        if not selected_content:
            return None
        return selected_content.get("price")

    def _cms_content_tier(self, selected_content: dict | None):
        contract = self._cms_offer_candidate(selected_content)
        if contract:
            cents = contract.price_cents
            if cents is None or cents <= 1500:
                return "low"
            if cents <= 3500:
                return "high"
            return "premium"
        if not selected_content:
            return None
        return selected_content.get("tier")

    def _cms_content_delivery_type(self, selected_content: dict | None):
        contract = self._cms_offer_candidate(selected_content)
        if contract and contract.product:
            return contract.product.delivery_type.value
        if not selected_content:
            return None
        return selected_content.get("delivery_type")

    def _cms_content_delivery_mode(self, selected_content: dict | None):
        contract = self._cms_offer_candidate(selected_content)
        if contract and contract.delivery_permission:
            return contract.delivery_permission.delivery_mode.value
        if not selected_content:
            return None
        return selected_content.get("delivery_permission_mode")

    def _cms_content_requires_payment(self, selected_content: dict | None):
        contract = self._cms_offer_candidate(selected_content)
        if contract and contract.delivery_permission:
            return contract.delivery_permission.requires_payment
        if not selected_content:
            return None
        return selected_content.get("delivery_requires_payment")

    def _cms_delivery_payload(self, selected_content: dict | None) -> dict:
        return {
            "delivery_type": self._cms_content_delivery_type(selected_content),
            "delivery_permission_mode": self._cms_content_delivery_mode(
                selected_content
            ),
            "delivery_requires_payment": self._cms_content_requires_payment(
                selected_content
            ),
        }

    def _cms_content_caption(self, selected_content: dict | None):
        contract = self._cms_offer_candidate(selected_content)
        if contract:
            if contract.description:
                return contract.description
            if contract.product and contract.product.description:
                return contract.product.description
            return contract.title
        if not selected_content:
            return None
        return selected_content.get("caption")

    def _compat_content_link(self, selected_content: dict | None):
        # Compatibility boundary: ConversationGateway and provider runtimes still
        # expect legacy content dictionaries with an authorized offer link.
        if not selected_content:
            return None
        return selected_content.get("fanvue_link")

    def _cms_content_deliverable(self, selected_content: dict | None) -> bool:
        contract = self._cms_offer_candidate(selected_content)
        if contract:
            return contract.is_deliverable
        return bool(selected_content)

    def _cms_price_from_cents(self, price_cents):
        price = (price_cents or 0) / 100
        return int(price) if price.is_integer() else price

    def _determine_subscriber_profile(self, user_memory: dict) -> tuple[str, str]:
        """
        Returns:
            (subscriber_profile, subscriber_profile_reason)
        """

        # --- Base checks ---
        is_subscriber = user_memory.get("is_subscriber", False)
        if not is_subscriber:
            return "none", "User is not a subscriber."

        # Signals (defensive defaults)
        purchase_count = int(user_memory.get("purchase_count", 0) or 0)
        message_count = int(user_memory.get("message_count", 0) or 0)
        last_active_at = user_memory.get("last_active_at")

        # --- Time normalization ---
        days_inactive = 0
        if last_active_at:
            try:
                if isinstance(last_active_at, str):
                    last_active_dt = datetime.fromisoformat(last_active_at.replace("Z", "+00:00"))
                else:
                    last_active_dt = last_active_at

                if last_active_dt.tzinfo is None:
                    last_active_dt = last_active_dt.replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                days_inactive = (now - last_active_dt).days
            except Exception:
                # If parsing fails, assume active (don’t misclassify as lapsed)
                days_inactive = 0

        # --- Future-ready: high value / whale hook ---
        # (kept simple and safe; you can swap to spend-based later)
        if user_memory.get("user_value_tier") == "whale" or purchase_count >= 10:
            return "HIGH_VALUE_SUBSCRIBER", "High purchase_count or whale-tier user."

        # --- LAPSED (strong signal first) ---
        if days_inactive >= 14:
            return "LAPSED_SUBSCRIBER", f"Inactive for {days_inactive} days."

        # --- NEW (recent + low engagement) ---
        # If very low purchases and low engagement and very recent activity
        if purchase_count <= 1 and message_count <= 3:
            if days_inactive <= 2:
                return "NEW_SUBSCRIBER", "Very recent subscriber with low engagement."
            else:
                return "NEW_SUBSCRIBER", "Low purchase count and low engagement."

        # --- ACTIVE (everything else that is not lapsed/new/high-value) ---
        return "ACTIVE_SUBSCRIBER", f"Active within {days_inactive} days, engagement present."
    
    def _build_subscriber_behavior_config(self, user_memory: dict) -> dict:
        """
        Build behavior configuration for subscriber handling.
        This does NOT change routing directly.
        It prepares downstream systems (GPT, timing, offers) to behave differently.
        """

        subscriber_profile = user_memory.get("subscriber_profile", "none")

        default_config = {
            "tone_style": "balanced",
            "response_length": "medium",
            "pacing_level": "normal",
            "monetization_pressure": "medium",
            "attention_priority": "medium",
        }

        if subscriber_profile == "NEW_SUBSCRIBER":
            return {
                "tone_style": "soft",
                "response_length": "medium",
                "pacing_level": "slow",
                "monetization_pressure": "low",
                "attention_priority": "high",
            }

        if subscriber_profile == "ACTIVE_SUBSCRIBER":
            return {
                "tone_style": "balanced",
                "response_length": "medium",
                "pacing_level": "normal",
                "monetization_pressure": "medium",
                "attention_priority": "high",
            }

        if subscriber_profile == "LAPSED_SUBSCRIBER":
            return {
                "tone_style": "reengagement",
                "response_length": "medium",
                "pacing_level": "slow",
                "monetization_pressure": "low",
                "attention_priority": "high",
            }

        if subscriber_profile == "HIGH_VALUE_SUBSCRIBER":
            return {
                "tone_style": "premium",
                "response_length": "medium",
                "pacing_level": "slow",
                "monetization_pressure": "low",
                "attention_priority": "critical",
            }

        return default_config
    
    def _resolve_durable_buyer_tier(
        self,
        user_memory: dict,
        intent_tier: str | None = None,
    ) -> str:
        """
        Buyer tier is durable spend/value classification.

        It should NOT be downgraded by the current message intent.
        A whale remains a whale even if today's message is casual.
        """

        memory_buyer_tier = str(
            user_memory.get("buyer_tier") or ""
        ).upper()

        user_value_tier = str(
            user_memory.get("user_value_tier") or ""
        ).upper()

        is_whale = bool(user_memory.get("is_whale"))
        is_top_spender = bool(user_memory.get("is_top_spender"))

        total_spend = float(
            user_memory.get("total_spend") or 0
        )

        purchase_count = int(
            user_memory.get("purchase_count") or 0
        )

        if (
            memory_buyer_tier == "WHALE"
            or user_value_tier == "WHALE"
            or is_whale
            or total_spend >= 1000
        ):
            return "WHALE"

        if (
            memory_buyer_tier in ["HIGH_VALUE", "HIGH-VALUE"]
            or user_value_tier in ["HIGH_VALUE", "HIGH-VALUE"]
            or is_top_spender
            or total_spend >= 300
        ):
            return "HIGH_VALUE"

        if (
            memory_buyer_tier == "ACTIVE_BUYER"
            or total_spend >= 75
            or purchase_count >= 5
        ):
            return "ACTIVE_BUYER"

        if (
            memory_buyer_tier == "LOW_SPENDER"
            or total_spend > 0
            or purchase_count > 0
        ):
            return "LOW_SPENDER"

        return str(intent_tier or "NON_BUYER").upper()

    def _parse_engine_user_id(self, user_id: str):
        """
        Converts 'account_id:user_id' → (account_id, user_id)
        Example: '2:4' → (2, '4')

        Account IDs are numeric database keys. User IDs remain text because
        user_memory and buyer_intelligence store fanvue_user_id as TEXT.
        """
        try:
            account_id_str, user_id_str = str(user_id).split(":")
            normalized_user_id = str(int(user_id_str))
            return int(account_id_str), normalized_user_id
        except Exception:
            self.logger.error(f"[RELATIONSHIP] Invalid user_id format: {user_id}")
            return None, None

    def _increment_counter(self, user_id: str, field_name: str, amount: int = 1) -> int:
        current_value = self.memory.get_field(user_id, field_name, 0) or 0
        new_value = current_value + amount
        self.memory.set_field(user_id, field_name, new_value)
        return new_value

    def _normalize_signals(self, raw_signals) -> list:
        """
        Ensure signals are always JSON-safe for Postgres JSONB storage.
        Converts sets/tuples/lists to a clean list of strings.
        """
        if not raw_signals:
            return []

        if isinstance(raw_signals, set):
            raw_signals = list(raw_signals)
        elif isinstance(raw_signals, tuple):
            raw_signals = list(raw_signals)
        elif not isinstance(raw_signals, list):
            raw_signals = [raw_signals]

        cleaned = []
        for signal in raw_signals:
            if signal is None:
                continue
            cleaned.append(str(signal))
        return cleaned

    def _normalize_route_signals(self, raw_signals) -> list:
        if not raw_signals:
            return []

        if isinstance(raw_signals, set):
            raw_signals = list(raw_signals)
        elif isinstance(raw_signals, tuple):
            raw_signals = list(raw_signals)
        elif not isinstance(raw_signals, list):
            raw_signals = [raw_signals]

        cleaned = []
        for signal in raw_signals:
            if signal is None:
                continue
            cleaned.append(str(signal))
        return cleaned
    
    def _should_enter_soft_transition(self, memory: dict) -> bool:
        """
        Determines if the system should enter a soft transition phase
        before sending an offer.

        This prevents immediate selling and introduces a natural
        bridge between engagement and monetization.
        """

        if not memory:
            return False

        # Core signals
        engagement_mode = memory.get("subscriber_engagement_mode")
        intent_score = int(memory.get("intent_score") or 0)
        messages_since_last_offer = int(memory.get("messages_since_last_offer") or 0)

        # Safety flags
        rewarm_required = memory.get("subscriber_rewarm_required", False)
        last_message_type = memory.get("last_message_type")
        offer_state = memory.get("offer_state")

        # --- CONDITIONS ---

        # Must be in tension mode (ready for escalation)
        if engagement_mode != "tension":
            return False

        # Must have enough intent
        if intent_score < 30:
            return False

        # Must not be immediately after an offer
        if messages_since_last_offer < 1:
            return False

        # Must not be in rewarm state
        if rewarm_required:
            return False

        # 🔥 NEW — Anti-spam guard (Step 6)

        # Do not soft-transition twice in a row
        if last_message_type == "soft_transition":
            return False

        # Do not soft-transition during active post-offer flow
        if offer_state in ["offered", "nudged"]:
            return False

        return True
    
    def _is_soft_transition_confirmation(self, memory: dict) -> bool:
        """
        19E — GPT-based soft transition confirmation.

        No hard-coded user phrases.
        """

        gpt_result = memory.get("gpt_classifier_result", {}) or {}

        confidence = float(gpt_result.get("confidence", 0.0) or 0.0)
        curiosity_level = gpt_result.get("curiosity_level")
        escalation_ready = bool(gpt_result.get("escalation_ready", False))
        recommended_action = gpt_result.get("recommended_action")

        if not self._is_gpt_confident(gpt_result):
            return False

        return (
            escalation_ready
            or curiosity_level in ["medium", "high"]
            or recommended_action in ["offer", "close", "build_tension"]
        )

    def _is_gpt_confident(self, gpt_result: dict, threshold: float = 0.6) -> bool:
        """
        19F — GPT Safety Check

        Ensures GPT output is reliable before acting on it.
        """

        try:
            confidence = float(gpt_result.get("confidence", 0.0) or 0.0)
            return confidence >= threshold
        except Exception:
            return False
    
    @staticmethod
    def _explicit_request_detected(message: str, classifier_result: dict) -> bool:
        """Use affirmative classifier values and user text, never dict key names."""
        classifier = classifier_result or {}
        if bool(classifier.get("sexual_engagement") or
                classifier.get("explicit_without_buying_intent")):
            return True
        text = str(message or "").lower()
        return any(re.search(pattern, text) for pattern in (
            r"\bsexually explicit\b", r"\bexplicit (?:content|photo|video|chat)\b",
            r"\bnsfw\b", r"\bdirty talk\b", r"\bsext(?:ing)?\b",
            r"\b(?:cock|penis|pussy|fuck(?:ing)?)\b",
        ))

    def _build_explicit_vs_buying_profile(
        self,
        message: str,
        classifier_result: dict,
        routing_result: dict,
    ) -> dict:
        """
        3D.19.16

        Separates sexual / explicit engagement from actual buying intent.

        IMPORTANT:
        Explicit engagement does NOT automatically mean:
        - send offer
        - close mode
        - PPV CTA
        - conversion pressure
        """

        classifier_result = classifier_result or {}
        routing_result = routing_result or {}

        explicit_requested = self._explicit_request_detected(
            message, classifier_result
        )

        buying_intent = bool(
            classifier_result.get("buying_intent")
        )

        close_ready = bool(
            classifier_result.get("close_ready")
        )

        recommended_action = (
            classifier_result.get("recommended_action")
            or ""
        )

        user_state = (
            classifier_result.get("user_state")
            or ""
        )

        monetization_intent = bool(
            buying_intent
            or close_ready
            or recommended_action in [
                "offer",
                "close",
                "custom_request",
            ]
            or user_state in [
                "ready_to_buy",
                "converted",
            ]
        )

        sexual_engagement_only = bool(
            explicit_requested
            and not monetization_intent
        )

        suppress_sales_pressure = bool(
            sexual_engagement_only
        )

        return {
            "explicit_requested": explicit_requested,
            "sexual_engagement_only": sexual_engagement_only,
            "monetization_intent": monetization_intent,
            "buying_intent": buying_intent,
            "close_ready": close_ready,
            "recommended_action": recommended_action,
            "user_state": user_state,
            "suppress_sales_pressure": suppress_sales_pressure,
            "reason": (
                "explicit_engagement_without_buying_intent"
                if sexual_engagement_only
                else "buying_or_non_explicit_context"
            ),
        }

    @staticmethod
    def _commerce_readiness(message, classifier_result, explicit_profile):
        """Return compact flags only; never prompt text or model reasoning."""
        text = str(message or "").lower()
        classifier = classifier_result or {}
        requested_purchase = any(
            word in text for word in (
                "buy", "purchase", "unlock", "pay", "paid", "ppv",
            )
        )
        requested_link = any(
            word in text for word in (
                "link", "url", "where can i get", "send it",
            )
        )
        requested_price = any(
            word in text for word in ("price", "cost", "how much")
        )
        requested_content = any(
            word in text for word in (
                "photo", "picture", "image", "set", "video", "content",
            )
        )
        suppressed = bool(
            (explicit_profile or {}).get("suppress_sales_pressure")
        )
        from app.services.conversational_sales_progression_service import (
            ConversationalSalesProgressionService,
        )
        transition = ConversationalSalesProgressionService.transition_features(
            message
        )
        requested_content = bool(
            requested_content or transition.get("content_request")
        )
        buying_intent = bool(
            classifier.get("buying_intent")
            or classifier.get("close_ready")
            or requested_purchase
            or requested_link
            or requested_price
            or transition.get("content_request")
        )
        conversational_action = (
            ConversationalSalesProgressionService
            .recommended_conversational_action(
                message, classifier, explicit_profile,
            )
        )
        return {
            "conversation_ready_for_offer": bool(
                conversational_action == "PRESENT_OFFER" and not suppressed
            ),
            "recommended_conversational_action": conversational_action,
            "recommended_offering_id": None,
            "offering_authority": "DETERMINISTIC_SELECTOR_ONLY",
            "current_buying_intent": buying_intent,
            "customer_requested_content": requested_content,
            "customer_requested_price": requested_price,
            "customer_requested_purchase": requested_purchase,
            "customer_requested_link": requested_link,
            **transition,
            "escalation_ready": bool(classifier.get("escalation_ready")),
            "recommended_action": classifier.get("recommended_action"),
            "user_state": classifier.get("user_state"),
            "curiosity_level": classifier.get("curiosity_level"),
            "buyer_likelihood": classifier.get("buyer_likelihood"),
            "engagement_level": classifier.get("engagement_level"),
            "classifier_buying_intent": bool(classifier.get("buying_intent")),
            "classifier_close_ready": bool(classifier.get("close_ready")),
        }

    def process_message(
            self, 
            user_id: str, 
            message: str, chat_history=None,
            runtime_injection: dict | None = None,
            
            ) -> DecisionEngineResult:
        if chat_history is None:
            chat_history = []
        
        runtime_injection = runtime_injection or {}
        commerce_execution_policy = runtime_injection.get(
            "commerce_execution_policy"
        )
        authoritative_commerce = bool(commerce_execution_policy)
        presentation_allowed = (
            commerce_execution_policy
            == CommerceExecutionPolicy.PRESENTATION_ALLOWED.value
        )
        nudge_allowed = (
            commerce_execution_policy
            == CommerceExecutionPolicy.NUDGE_ALLOWED.value
        )
        acknowledgement_allowed = (
            commerce_execution_policy
            == CommerceExecutionPolicy.ACKNOWLEDGEMENT_ALLOWED.value
        )
        # Commercial action is fail-closed unless the canonical caller has
        # already evaluated Customer Sales Brain. DecisionEngine never runs
        # its historical commercial authority path.
        legacy_commerce_enabled = False
        legacy_commerce_evaluation_allowed = False

        if runtime_injection:
            self.logger.info(
                f"[3D.17.6 RUNTIME INJECTION] "
                f"{runtime_injection}"
            )
        if authoritative_commerce:
            self.logger.info(
                "event=commerce_execution_policy_applied policy=%s",
                commerce_execution_policy,
            )
            if not presentation_allowed:
                self.logger.info(
                    "event=legacy_commerce_suppressed policy=%s",
                    commerce_execution_policy,
                )

        # 1. Load memory
        user_memory = self.memory.get_user_memory(user_id)
        pre_message_last_active_at = user_memory.get("last_active_at")

        # 🔥 Subscriber Identification Sync (DB → Memory)
        fanvue_account_id, fanvue_user_id = self._parse_engine_user_id(user_id)
        telegram_only_identity = bool(
            fanvue_user_id is not None and fanvue_user_id.startswith("-")
        )
        mapped_fanvue_user_id = (
            None if telegram_only_identity else fanvue_user_id
        )
        self.logger.info(
            "[IDENTITY FLOW] layer=DecisionEngine "
            "fanvue_account_id=%r fanvue_account_id_type=%s "
            "fanvue_user_id=%r fanvue_user_id_type=%s "
            "mapped_fanvue_user_id=%r telegram_only=%s",
            fanvue_account_id,
            type(fanvue_account_id).__name__,
            fanvue_user_id,
            type(fanvue_user_id).__name__,
            mapped_fanvue_user_id,
            telegram_only_identity,
        )

        creator_profile = {}

        if fanvue_account_id is not None:
            creator_profile = (
                self.decision_runtime_boundary.get_active_creator_profile(
                    fanvue_account_id
                )
                or {}
            )

        self.logger.info(
            f"[CREATOR PROFILE] account_id={fanvue_account_id} | "
            f"loaded={bool(creator_profile)} | "
            f"persona={creator_profile.get('persona_name')}"
        )

        require_creator_profile = getattr(
            self.settings,
            "REQUIRE_CREATOR_PROFILE",
            True,
        )

        if not creator_profile and require_creator_profile:
            self.logger.error(
                f"[CREATOR PROFILE REQUIRED] Blocking response generation. "
                f"fanvue_account_id={fanvue_account_id} user_id={user_id}"
            )

            blocked_response = (
                "Creator Profile is required before this account can generate replies."
            )
            self.logger.info(
                "[DECISION ENGINE RETURN] response_text_length=%s "
                "response_text_preview=%r blocked=%s send_offer=%s",
                len(blocked_response),
                blocked_response[:100],
                True,
                False,
            )

            return self._runtime_decision_result({
                "response": blocked_response,
                "error": "creator_profile_required",
                "fanvue_account_id": fanvue_account_id,
                "fanvue_user_id": fanvue_user_id,
                "blocked": True,
            })

        if not creator_profile:
            # Temporary MVP fallback only. This is not stored and does not
            # replace the account-scoped creator-profile functionality.
            creator_profile = {
                "persona_name": self.settings.DEFAULT_PERSONA,
                "display_name": self.settings.DEFAULT_PERSONA,
            }
            self.logger.warning(
                f"[CREATOR PROFILE BYPASS] Continuing with minimal runtime "
                f"persona context. fanvue_account_id={fanvue_account_id} "
                f"user_id={user_id}"
            )

        user_record = None
        if fanvue_account_id is not None and fanvue_user_id is not None:
            user_record = self.decision_runtime_boundary.get_user_by_account_and_id(
                fanvue_account_id,
                int(fanvue_user_id),
            )

        if user_record:
            is_subscriber = user_record.get("is_subscriber", False)
            is_follower = user_record.get("is_follower", False)
            relationship_status = user_record.get("relationship_status", "unknown")

            # Update memory so engine can use it
            self.memory.update_user_memory(
                user_id,
                {
                    "is_subscriber": is_subscriber,
                    "is_follower": is_follower,
                    "relationship_status": relationship_status,
                },
            )

            # Refresh memory with latest values
            user_memory = {
                **user_memory,
                "is_subscriber": is_subscriber,
                "is_follower": is_follower,
                "relationship_status": relationship_status,
            }

            self.logger.info(
                f"[RELATIONSHIP] subscriber={is_subscriber} | follower={is_follower} | status={relationship_status}"
            )

        # Ensure relationship_status always exists, even if no DB user_record is found.
        relationship_status = (user_memory.get("relationship_status") or "unknown").lower()

        # 9E. Outreach → Monetization Handoff
        # If this inbound message is a response to outreach,
        # stop outreach and hand the user back to chat/DecisionEngine.
        if self.outreach_service.should_trigger_outreach_handoff(user_memory):
            outreach_handoff_updates = self.outreach_service.handle_outreach_response(
                user_memory
            )

            self.memory.update_user_memory(
                user_id,
                outreach_handoff_updates,
            )

            user_memory = {
                **user_memory,
                **outreach_handoff_updates,
            }

            self.logger.info(
                f"[OUTREACH HANDOFF] persisted user_id={user_id} "
                f"updates={outreach_handoff_updates}"
            )
        
        # --------------------------------------------------
        # 19E — GPT CLASSIFIER RESULT FOR THIS MESSAGE
        # --------------------------------------------------

        gpt_classifier_result = self.gpt_intent_classifier.classify_message(
            message=message,
            memory=user_memory,
        )

        self.logger.info(f"[19E GPT CLASSIFIER] {gpt_classifier_result}")

        # --------------------------------------------------
        # 15.5 OBJECTION DETECTION (READ-ONLY)
        # --------------------------------------------------

        objection_result = self.objection_classifier.classify_objection(
            message=message,
            memory=user_memory,
        )

        self.logger.info("[15.5 OBJECTION BLOCK EXECUTED]")

        self.logger.info(f"[15.5 OBJECTION RESULT] {objection_result}")
       
        # 2. Situation routing
        routing_result = self.situation_routing_service.route_message(
            message,
            user_memory,
            classifier_result=gpt_classifier_result,
        )

        route = routing_result.get("route", "chat")

        explicit_vs_buying_profile = (
            self._build_explicit_vs_buying_profile(
                message=message,
                classifier_result=gpt_classifier_result,
                routing_result=routing_result,
            )
        )

        self.logger.info(
            f"[3D.19.16 EXPLICIT VS BUYING] "
            f"{explicit_vs_buying_profile}"
        )

        # 🔥 Relationship-aware route tagging
        is_subscriber = user_memory.get("is_subscriber", False)
        is_follower = user_memory.get("is_follower", False)
        is_whale = user_memory.get("is_whale", False)

        relationship_route = None

        if is_whale:
            relationship_route = "whale"
        elif is_subscriber:
            relationship_route = "subscriber"
        elif is_follower:
            relationship_route = "follower"

        route_confidence = routing_result.get("confidence", 0.50)
        route_reason = routing_result.get("reason", "No routing reason provided.")
        route_signals = self._normalize_route_signals(routing_result.get("signals", []))

        # 🔥 7G — Rewarm Route Override
        subscriber_rewarm_required = bool(user_memory.get("subscriber_rewarm_required", False))

        # 🔥 7H — Rewarm Exit Logic (Warm Detection)

        rewarm_exit_signals = []

        intent_score = int(user_memory.get("intent_score") or 0)
        message_count = int(user_memory.get("message_count") or 0)
        messages_since_last_offer = int(user_memory.get("messages_since_last_offer") or 0)
        exclusive_interest = int(user_memory.get("exclusive_interest_count") or 0)
        closing_questions = int(user_memory.get("closing_questions_count") or 0)

        # Detect warming behavior
        if intent_score >= 15:
            rewarm_exit_signals.append("intent_recovered")

        if message_count >= 3:
            rewarm_exit_signals.append("conversation_active")

        if messages_since_last_offer >= 2:
            rewarm_exit_signals.append("engaging_after_rewarm")

        if exclusive_interest > 0:
            rewarm_exit_signals.append("exclusive_interest")

        if closing_questions > 0:
            rewarm_exit_signals.append("closing_behavior")

        if subscriber_rewarm_required and len(rewarm_exit_signals) >= 2:
            subscriber_rewarm_required = False

            self.memory.update_user_memory(
                user_id,
                {
                    "subscriber_rewarm_required": False,
                    "subscriber_fatigue_flag": False,
                },
            )

            user_memory = {
                **user_memory,
                "subscriber_rewarm_required": False,
                "subscriber_fatigue_flag": False,
            }

            self.logger.info(
                f"[REWARM EXIT] signals={rewarm_exit_signals} → rewarm disabled and persisted"
            )

        if subscriber_rewarm_required:
            route = "chat"
            route_confidence = 1.0
            route_reason = "Rewarm required: forcing chat route before monetization."
            route_signals = self._normalize_route_signals(
                list(route_signals) + ["rewarm_route_override"]
            )
            self.logger.info("[REWARM ROUTE OVERRIDE] forcing chat mode")

        # ✅ 3B — Soft subscriber precedence hook
        if relationship_route == "subscriber" and route == "chat":
            if "subscriber_priority" not in route_signals:
                route_signals.append("subscriber_priority")
            self.logger.info("[ROUTING PRECEDENCE] subscriber_priority_applied")

        self.logger.info(f"[RELATIONSHIP ROUTE] {relationship_route}")

        # FORCE SALES ROUTE IF USER IS STILL IN POST-OFFER STATE
        last_offer_timestamp = user_memory.get("last_offer_timestamp")
        offer_state = user_memory.get("offer_state")

        if (
            legacy_commerce_enabled
            and last_offer_timestamp
            and offer_state in ["offered", "nudged"]
        ):
            route = "sales"
            route_reason = "Forced to sales due to active post-offer state."
            route_signals = self._normalize_route_signals(
                list(route_signals) + ["post_offer_sales_lock"]
            )
            route_confidence = max(route_confidence, 0.95)
            self.logger.info("🔥 FORCING SALES ROUTE (POST-OFFER STATE)")

        # ✅ 3E — Safe subscriber override conditions
        effective_route = route

        subscriber_profile = user_memory.get("subscriber_profile")
        offer_state = (
            user_memory.get("offer_state")
            if legacy_commerce_enabled
            else None
        )

        subscriber_override_allowed = (
            relationship_route == "subscriber"
            and route == "chat"
            and subscriber_profile not in (None, "", "none")
            and offer_state not in ["offered", "nudged"]
        )

        if subscriber_override_allowed:
            effective_route = "subscriber"
            route_signals = self._normalize_route_signals(
                list(route_signals) + ["subscriber_safe_override"]
            )
            self.logger.info("[SUBSCRIBER SAFE OVERRIDE] effective_route=subscriber")
        
        # ✅ 4B.2 — Subscriber sales pressure control
        subscriber_behavior_config = self._build_subscriber_behavior_config(user_memory)
        subscriber_pacing_level = subscriber_behavior_config.get("pacing_level", "normal")
        subscriber_pressure_level = subscriber_behavior_config.get("monetization_pressure", "medium")

        weak_sales_reason = route_reason in [
            "No stronger route detected.",
            "Routed to sales by priority after tie. Primary signal: previous_route_bias.",
        ]

        subscriber_sales_soft_block = (
            relationship_route == "subscriber"
            and route == "sales"
            and offer_state not in ["offered", "nudged"]
            and subscriber_pacing_level == "slow"
            and subscriber_pressure_level == "low"
            and weak_sales_reason
        )

        if subscriber_sales_soft_block:
            route = "chat"
            effective_route = "subscriber"
            route_reason = "Subscriber pacing control blocked early sales routing."
            route_signals = self._normalize_route_signals(
                list(route_signals) + ["subscriber_sales_soft_block"]
            )
            self.logger.info("[SUBSCRIBER SALES CONTROL] blocked_early_sales_route")

        # Keep route history in-memory only for now (no DB persistence yet)
        existing_route_history = user_memory.get("route_history", []) or []
        if not isinstance(existing_route_history, list):
            existing_route_history = [str(existing_route_history)]

        route_history = existing_route_history + [route]
        route_history = route_history[-10:]

        self.logger.info(f"[ROUTING] Route: {route} | Confidence: {route_confidence}")
        self.logger.info(f"[ROUTING] Signals: {route_signals}")
        self.logger.info(f"[ROUTING] Reason: {route_reason}")

        # 3. Track behavior
        lowered_message = message.lower().strip()
        
        # 🔥 Subscriber Engagement Depth Tracking
        engagement_depth_score = user_memory.get("engagement_depth_score", 0) or 0

        word_count = len(message.split())

        if word_count > 8:
            engagement_depth_score += 2
        elif word_count > 3:
            engagement_depth_score += 1

        engagement_depth_score = min(engagement_depth_score, 50)

        self.memory.set_field(user_id, "engagement_depth_score", engagement_depth_score)

        # 🔥 Conversation Streak Tracking
        conversation_streak = user_memory.get("conversation_streak", 0) or 0
        conversation_streak += 1
        conversation_streak = min(conversation_streak, 100)

        self.memory.set_field(user_id, "conversation_streak", conversation_streak)

        # 🔥 Engagement Tier Classification
        if engagement_depth_score >= 5 or conversation_streak >= 5:
            engagement_tier = "HIGH"
        elif engagement_depth_score >= 2 or conversation_streak >= 3:
            engagement_tier = "MEDIUM"
        else:
            engagement_tier = "LOW"

        self.memory.set_field(user_id, "engagement_tier", engagement_tier)

        # 🔥 Subscriber Engagement Mode Assignment
        if engagement_tier == "LOW":
            subscriber_engagement_mode = "casual"
        elif engagement_tier == "MEDIUM":
            subscriber_engagement_mode = "flirty"
        else:
            subscriber_engagement_mode = "tension"

        self.memory.set_field(user_id, "subscriber_engagement_mode", subscriber_engagement_mode)

        self.logger.info(
            f"[SUBSCRIBER ENGAGEMENT] depth_score={engagement_depth_score} | "
            f"words={word_count} | streak={conversation_streak} | "
            f"tier={engagement_tier} | mode={subscriber_engagement_mode}"
        )

        inbound_memory = self.memory.increment_inbound_message(user_id)
        message_count = inbound_memory.get("message_count", 0) or 0

        price_questions_count = self.memory.get_field(user_id, "price_questions_count", 0) or 0
        exclusive_interest_count = self.memory.get_field(user_id, "exclusive_interest_count", 0) or 0
        closing_questions_count = self.memory.get_field(user_id, "closing_questions_count", 0) or 0
        offers_shown_count = self.memory.get_field(user_id, "offers_shown_count", 0) or 0

        # --------------------------------------------------
        # 19M PHASE 6 — GPT-BASED PHRASE COUNTER REPLACEMENT
        # --------------------------------------------------

        classifier_result = gpt_classifier_result or {}

        # --------------------------------------------------
        # 15.6 RESPONSE BEHAVIOR ENGINE
        # --------------------------------------------------

        behavior = self.response_behavior_service.determine_behavior(
            classifier_result=classifier_result,
            memory=user_memory,
        )

        print("\n[15.6 BEHAVIOR ENGINE]")
        print("strategy:", behavior.get("response_strategy"))
        print("pressure:", behavior.get("pressure_level"))
        print("tone:", behavior.get("tone_mode"))
        print("sell:", behavior.get("should_sell"))
        print("offer:", behavior.get("should_send_offer"))
        print("objection:", behavior.get("should_handle_objection"))
        print("downgrade:", behavior.get("should_downgrade_effort"))
        print("notes:", behavior.get("behavior_notes"))

        gpt_objection_type = objection_result.get("objection_type")
        gpt_route = classifier_result.get("route")
        gpt_recommended_action = classifier_result.get("recommended_action")
        gpt_buying_intent = bool(classifier_result.get("buying_intent", False))
        gpt_close_ready = bool(classifier_result.get("close_ready", False))
        gpt_user_state = classifier_result.get("user_state")
        gpt_confident = self._is_gpt_confident(classifier_result)

        if gpt_confident:
            if gpt_objection_type == "price":
                price_questions_count = self._increment_counter(
                    user_id,
                    "price_questions_count",
                )

            if gpt_route == "custom_request" or gpt_recommended_action == "custom_request":
                exclusive_interest_count = self._increment_counter(
                    user_id,
                    "exclusive_interest_count",
                )

            if (
                gpt_buying_intent
                or gpt_close_ready
                or gpt_user_state == "ready_to_buy"
                or gpt_recommended_action in ["offer", "close"]
            ):
                closing_questions_count = self._increment_counter(
                    user_id,
                    "closing_questions_count",
                )
        else:
            self.logger.info(
                "[19M PHASE 6] Low GPT confidence → skipping phrase counter updates"
            )

        # Reload memory after counter updates
        user_memory = self.memory.get_user_memory(user_id)

        # 4. Intent
        intent_result = self.intent.detect_intent(
            message,
            user_memory,
            classifier_result=gpt_classifier_result,
        )
        
        normalized_signals = self._normalize_signals(intent_result.get("signals", []))
        intent_result["signals"] = normalized_signals

        durable_buyer_tier = self._resolve_durable_buyer_tier(
            user_memory=user_memory,
            intent_tier=intent_result.get("tier"),
        )

        intent_result["message_intent_tier"] = intent_result.get(
            "tier"
        )

        intent_result["tier"] = durable_buyer_tier

        self.logger.info(
            f"[DURABLE BUYER TIER] "
            f"message_intent_tier={intent_result.get('message_intent_tier')} | "
            f"durable_buyer_tier={durable_buyer_tier}"
        )

        # 5. User value calculation
        pre_attention_memory = {
            **user_memory,
            "message_count": message_count,
            "price_questions_count": price_questions_count,
            "exclusive_interest_count": exclusive_interest_count,
            "closing_questions_count": closing_questions_count,
            "offers_shown_count": offers_shown_count,
            "buyer_tier": intent_result["tier"],
            "intent_score": intent_result["score"],
            "message_score": intent_result["message_score"],
            "behavior_score": intent_result["behavior_score"],
            "intent_signals": list(normalized_signals) if normalized_signals else [],
            "last_user_message": message,
            "last_active_at": pre_message_last_active_at,
            "engagement_depth_score": engagement_depth_score,
            "conversation_streak": conversation_streak,
            "engagement_tier": engagement_tier,
            "subscriber_engagement_mode": subscriber_engagement_mode,
        }

        user_value_tier = self.user_value.determine_user_value(pre_attention_memory)
        is_whale = user_value_tier == "whale"

        attention_result = self.user_value.evaluate_attention(pre_attention_memory)
        user_type = attention_result.get("user_type", "unknown")
        value_score = attention_result.get("value_score", 50)
        attention_tier = attention_result.get("attention_tier", "medium")
        effort_mode = attention_result.get("effort_mode", "balanced")
        timewaster_flags = attention_result.get("timewaster_flags", [])

        # Canonical provider-backed value wins over legacy user_memory. Legacy
        # attention remains useful behavioral evidence, never buyer truth.
        from app.services.customer_value_attention_service import CustomerValueAttentionService
        canonical_value = dict(runtime_injection.get("customer_value_attention") or {})
        value_attention = None
        if canonical_value.get("schemaVersion") == "customer_value_attention_v1":
            # ConversationGateway carries the CustomerSalesBrain projection for
            # this exact turn.  It is already canonical and must not be fed back
            # through the legacy projector (which loses contextual hostility and
            # can silently restore BALANCED effort).
            value_attention_mapping = canonical_value
            compatibility = self._canonical_attention_compatibility(
                canonical_value
            )
        else:
            value_attention = CustomerValueAttentionService().project(
                commerce_memory=canonical_value,
                behavior={
                **pre_attention_memory,
                "presented_opportunity_count": canonical_value.get(
                    "presentedOpportunityCount", 0
                ),
                "failed_nonconverted_opportunity_count": canonical_value.get(
                    "failedNonconvertedOpportunityCount", 0
                ),
                "converted_opportunity_count": canonical_value.get(
                    "convertedOpportunityCount", 0
                ),
                "active_unresolved_opportunity": canonical_value.get(
                    "activeUnresolvedOpportunity", False
                ),
                "direct_buying_intent": bool(
                    classifier_result.get("buying_intent")
                    or classifier_result.get("close_ready")
                ),
                "sexual_engagement_only": bool(
                    classifier_result.get("explicit_without_buying_intent")
                ),
                "sales_progression_phase": dict(
                    (runtime_injection.get("commerce_decision") or {}).get(
                        "sales_progression"
                    ) or {}
                ).get("phase"),
                "active_purchase_intent": bool(
                    (runtime_injection.get("commerce_decision") or {}).get(
                        "current_offer_status"
                    )
                ),
            },
                legacy={
                    **attention_result,
                    "user_value_tier": user_value_tier,
                    "is_whale": is_whale,
                },
            )
            value_attention_mapping = dict(value_attention.to_mapping())
            compatibility = dict(value_attention.compatibility)
        user_value_tier = str(compatibility["user_value_tier"])
        is_whale = bool(compatibility["is_whale"])
        attention_tier = str(compatibility["attention_tier"])
        effort_mode = str(compatibility["effort_mode"])
        timewaster_flags = list(compatibility["timewaster_flags"])
        canonical_buyer_value = (
            value_attention_mapping.get("authority")
            == "COMMERCE_BACKED_AUTHORITATIVE_VALUE"
        )
        if canonical_buyer_value:
            canonical_tier_map = {
                "WHALE": "WHALE",
                "HIGH_VALUE": "HIGH_VALUE",
                "REPEAT_BUYER": "ACTIVE_BUYER",
                "BUYER": "LOW_SPENDER",
                "ENGAGED_PROSPECT": "NON_BUYER",
                "PROSPECT": "NON_BUYER",
                "LOW_VALUE_PROSPECT": "NON_BUYER",
            }
            intent_result["tier"] = canonical_tier_map.get(
                value_attention_mapping.get("valueTier"), "NON_BUYER"
            )
            relationship_route = (
                "whale" if is_whale else
                "subscriber" if is_subscriber else
                "follower" if is_follower else None
            )
        canonical_buyer_memory = {
            **user_memory,
            "buyer_status": value_attention_mapping.get("buyerStatus"),
            "buyer_stage": value_attention_mapping.get("buyerStage"),
            "buyer_tier": value_attention_mapping.get("valueTier"),
            "user_value_tier": value_attention_mapping.get("valueTier"),
            "is_whale": value_attention_mapping.get("valueTier") == "WHALE",
            "is_top_spender": value_attention_mapping.get("valueTier") in {
                "HIGH_VALUE", "WHALE",
            },
            "purchase_count": value_attention_mapping.get("purchaseCount", 0),
            "total_spend": (
                float(value_attention_mapping.get("lifetimeSpendMinor") or 0)
                / 100.0
            ),
            "recent_purchase_active": (
                value_attention_mapping.get("retentionLifecycle")
                == "ACTIVE_BUYER"
            ),
            "last_purchase_at": value_attention_mapping.get("lastPurchaseAt"),
            "relationship_investment": value_attention_mapping.get(
                "relationshipInvestment"
            ),
            "current_commercial_momentum": value_attention_mapping.get(
                "commercialMomentum"
            ),
            "dormant_whale": bool(
                value_attention_mapping.get("valueTier") == "WHALE"
                and value_attention_mapping.get("retentionLifecycle")
                    == "DORMANT_BUYER"
            ),
            "whale_reactivation_mode": (
                value_attention_mapping.get("reactivationState")
                == "REACTIVATED_BUYER"
            ),
            "customer_value_authority": value_attention_mapping.get("authority"),
        }

        # ✅ 3C + 3D — Prevent follower/outreach-style flags from applying to subscribers
        if relationship_route == "subscriber":
            subscriber_excluded_flags = {
                # follower-only
                "follower_bias_low_efficiency",
                "cold_follower_bias",
                "low_intent_with_high_chat_volume",
                "chatty_no_progress",

                # outreach / cold-user style
                "cold_user",
                "reactivation_candidate",
                "outreach_candidate",
                "ignored_user",
                "low_priority_warmup_target",
            }

            original_flags = list(timewaster_flags) if timewaster_flags else []
            timewaster_flags = [
                flag for flag in original_flags
                if flag not in subscriber_excluded_flags
            ]

            self.logger.info(
                f"[SUBSCRIBER PATH SEPARATION] filtered_flags={timewaster_flags}"
            )
            self.logger.info("[SUBSCRIBER OUTREACH PROTECTION] subscriber_excluded_from_outreach_style_flags")

        self.logger.info(
            f"[ATTENTION] user_type={user_type} | value_score={value_score} | "
            f"attention_tier={attention_tier} | effort_mode={effort_mode}"
        )
        self.logger.info(f"[ATTENTION] flags={timewaster_flags}")

        # 🔥 Silent Buyer Evaluation
        silent_buyer_result = self.silent_buyer.evaluate_silent_buyer(user_id)

        silent_buyer_score = silent_buyer_result.get("silent_buyer_score", 0)
        silent_buyer_tier = silent_buyer_result.get("silent_buyer_tier", "none")

        self.logger.info(
            f"[SILENT BUYER] score={silent_buyer_score} | tier={silent_buyer_tier}"
        )

        # 6. Mode
        conversation_mode = self.mode.determine_mode(intent_result["score"])

        

        # 🔥 Subscriber profile classification
        subscriber_profile, subscriber_profile_reason = self._determine_subscriber_profile(pre_attention_memory)

        self.logger.info(
            f"[SUBSCRIBER PROFILE] profile={subscriber_profile} | reason={subscriber_profile_reason}"
        )

        behavior_config = self._build_subscriber_behavior_config(
            {
                **pre_attention_memory,
                "subscriber_profile": subscriber_profile,
            }
        )

        # ✅ 4F — Attention Priority Boost
        attention_priority = "normal"

        if relationship_status == "subscriber":
            if subscriber_profile == "HIGH_VALUE_SUBSCRIBER":
                attention_priority = "critical"
            elif subscriber_profile in ["ACTIVE_SUBSCRIBER", "LAPSED_SUBSCRIBER", "NEW_SUBSCRIBER"]:
                attention_priority = "high"
        else:
            attention_priority = "low"

        behavior_config["attention_priority"] = attention_priority

        self.logger.info(f"[ATTENTION PRIORITY] level={attention_priority}")

        self.logger.info(
            f"[BEHAVIOR CONFIG] profile={subscriber_profile} | "
            f"tone={behavior_config.get('tone_style')} | "
            f"length={behavior_config.get('response_length')} | "
            f"pacing={behavior_config.get('pacing_level')} | "
            f"pressure={behavior_config.get('monetization_pressure')} | "
            f"attention={behavior_config.get('attention_priority')}"
        )

        self.memory.update_user_memory(
            user_id,
            {
                "subscriber_profile": subscriber_profile,
                "subscriber_profile_reason": subscriber_profile_reason,
            },
        )

        # ✅ 2E.1 — Sync into in-memory state immediately
        user_memory["subscriber_profile"] = subscriber_profile
        user_memory["subscriber_profile_reason"] = subscriber_profile_reason


        # --------------------------------------------------
        # 3D.17.6 — DECISIONENGINE RUNTIME INJECTION
        # --------------------------------------------------

        runtime_response_strategy = (
            runtime_injection.get(
                "response_strategy"
            )
        )

        runtime_escalation_level = (
            runtime_injection.get(
                "escalation_level"
            )
        )

        runtime_retention_mode = (
            runtime_injection.get(
                "retention_mode"
            )
        )

        runtime_ppv_energy = (
            runtime_injection.get(
                "ppv_energy"
            )
        )

        runtime_emotional_continuation = (
            runtime_injection.get(
                "emotional_continuation"
            )
        )

        runtime_followup_behavior = (
            runtime_injection.get(
                "followup_behavior"
            )
        )

        runtime_premium_routing = (
            runtime_injection.get(
                "premium_routing"
            )
        )

        runtime_cooldown_sensitivity = (
            runtime_injection.get(
                "cooldown_sensitivity"
            )
        )

        runtime_suppression_handling = (
            runtime_injection.get(
                "suppression_handling"
            )
        )


        # --------------------------------------------------
        # 3D.10.15H — INTIMACY ENGINE OVERRIDES
        # --------------------------------------------------

        intimacy_overrides = (
            self.intimacy_integration_service.build_overrides(
                user_memory,
                runtime_state={
                    "active_buying_window": bool(
                        dict(runtime_injection.get("active_buying_window") or {}).get(
                            "active"
                        )
                    ),
                    "current_commercial_momentum": value_attention_mapping.get(
                        "commercialMomentum"
                    ) or dict(
                        runtime_injection.get("active_buying_window") or {}
                    ).get("currentCommercialMomentum"),
                },
                canonical_buyer_memory=canonical_buyer_memory,
            )
        )

        smooth_escalation_profile = (
            self.smooth_intimacy_escalation_service.build_escalation_profile(
                intimacy_context=intimacy_overrides,
                spend_profile=user_memory,
                buyer_memory=canonical_buyer_memory,
                conversation_state={
                    "conversation_mode": conversation_mode,
                    "heat_score": user_memory.get("heat_score"),
                    "intent_score": intent_result.get("score"),

                    "buyer_session_active": user_memory.get(
                        "buyer_session_active"
                    ),

                    "buyer_session_step": user_memory.get(
                        "buyer_session_step"
                    ),

                    "buyer_session_action": user_memory.get(
                        "buyer_session_action"
                    ),
                    "buyer_momentum_score": user_memory.get(
                        "buyer_momentum_score"
                    ),

                    "relationship_depth_score": user_memory.get(
                        "relationship_depth_score"
                    ),

                    "conversation_streak": user_memory.get(
                        "conversation_streak"
                    ),

                    "engagement_depth_score": user_memory.get(
                        "engagement_depth_score"
                    ),

                    "intimacy_cooldown_active": user_memory.get(
                        "intimacy_cooldown_active"
                    ),

                    "recent_escalation_active": user_memory.get(
                        "recent_escalation_active"
                    ),

                    "cooldown_decay_level": user_memory.get(
                        "cooldown_decay_level"
                    ),

                    "post_purchase_cooldown": user_memory.get(
                        "post_purchase_cooldown"
                    ),
                },
            )
        )

        whale_retention_profile = (
            self.whale_retention_psychology_service.build_retention_profile(
                buyer_memory=canonical_buyer_memory,
                conversation_state={
                    "conversation_mode": conversation_mode,
                    "intent_score": intent_result.get("score"),
                    "sexual_engagement_only": explicit_vs_buying_profile.get(
                        "sexual_engagement_only"
                    ),
                    "monetization_intent": explicit_vs_buying_profile.get(
                        "monetization_intent"
                    ),
                },
                runtime_state={
                    **intimacy_overrides,
                    "buyer_tier": intent_result.get("tier"),
                    "user_value_tier": user_value_tier,
                    "is_whale": is_whale,
                    "premium_freshness_state": intimacy_overrides.get(
                        "premium_freshness_state"
                    ),
                    "dormant_whale": intimacy_overrides.get("dormant_whale"),
                    "whale_reactivation_mode": intimacy_overrides.get(
                        "whale_reactivation_mode"
                    ),
                },
            )
        )

        self.logger.info(
            f"[3D.20.1 WHALE RETENTION PSYCHOLOGY] "
            f"{whale_retention_profile}"
        )

        self.logger.info(
            f"[3D.11.2 SMOOTH ESCALATION] {smooth_escalation_profile}"
        )

        premium_relationship_memory_profile = (
            self.premium_relationship_memory_service
            .build_relationship_memory_profile(
                buyer_memory=canonical_buyer_memory,
                conversation_state={
                    "conversation_mode": conversation_mode,
                    "intent_score": intent_result.get("score"),
                    "buyer_tier": intent_result.get("tier"),
                    "user_value_tier": user_value_tier,
                },
                whale_retention_profile=whale_retention_profile,
            )
        )

        self.logger.info(
            f"[3D.20.2 PREMIUM RELATIONSHIP MEMORY] "
            f"{premium_relationship_memory_profile}"
        )

        emotional_presence_profile = (
            self.emotional_presence_refinement_service
            .build_emotional_presence_profile(
                buyer_memory=canonical_buyer_memory,
                conversation_state={
                    "conversation_mode": conversation_mode,
                    "intent_score": intent_result.get("score"),
                    "heat_score": user_memory.get("heat_score"),
                    "buyer_tier": intent_result.get("tier"),
                    "user_value_tier": user_value_tier,
                },
                whale_retention_profile=whale_retention_profile,
                premium_relationship_memory_profile=(
                    premium_relationship_memory_profile
                ),
            )
        )

        self.logger.info(
            f"[3D.20.3 EMOTIONAL PRESENCE REFINEMENT] "
            f"{emotional_presence_profile}"
        )

        premium_conversation_continuity_profile = (
            self.premium_conversation_continuity_service
            .build_continuity_profile(
                buyer_memory=canonical_buyer_memory,
                conversation_state={
                    "conversation_mode": conversation_mode,
                    "intent_score": intent_result.get("score"),
                    "heat_score": user_memory.get("heat_score"),
                    "buyer_tier": intent_result.get("tier"),
                    "user_value_tier": user_value_tier,
                },
                whale_retention_profile=whale_retention_profile,
                premium_relationship_memory_profile=(
                    premium_relationship_memory_profile
                ),
                emotional_presence_profile=emotional_presence_profile,
            )
        )

        self.logger.info(
            f"[3D.20.4 PREMIUM CONVERSATION CONTINUITY] "
            f"{premium_conversation_continuity_profile}"
        )

        whale_burnout_profile = (
            self.whale_burnout_prevention_service
            .build_burnout_profile(
                buyer_memory=canonical_buyer_memory,
                conversation_state={
                    "conversation_mode": conversation_mode,
                    "intent_score": intent_result.get("score"),
                    "heat_score": user_memory.get("heat_score"),
                    "buyer_tier": intent_result.get("tier"),
                    "user_value_tier": user_value_tier,
                },
                whale_retention_profile=whale_retention_profile,
                premium_relationship_memory_profile=(
                    premium_relationship_memory_profile
                ),
                emotional_presence_profile=emotional_presence_profile,
                premium_conversation_continuity_profile=(
                    premium_conversation_continuity_profile
                ),
            )
        )

        self.logger.info(
            f"[3D.20.5 WHALE BURNOUT PREVENTION] "
            f"{whale_burnout_profile}"
        )

        # --------------------------------------------------
        # 3D.20.6 — EMOTIONAL DEPENDENCY SAFEGUARDS
        # --------------------------------------------------

        emotional_dependency_profile = (
            self.emotional_dependency_classifier
            .classify_dependency_risk(
                message=message,
                memory=user_memory,
                continuity_context=(
                    premium_conversation_continuity_profile
                ),
                burnout_context=whale_burnout_profile,
                runtime_context={
                    "conversation_mode": conversation_mode,
                    "buyer_tier": intent_result.get("tier"),
                    "user_value_tier": user_value_tier,
                    "is_whale": is_whale,
                    "relationship_route": relationship_route,
                    "effective_route": effective_route,
                },
            )
        )

        self.logger.info(
            f"[3D.20.6 EMOTIONAL DEPENDENCY SAFEGUARDS] "
            f"{emotional_dependency_profile}"
        )

        long_term_stability_profile = (
            self.long_term_emotional_stability_service
            .build_stability_profile(
                buyer_memory=canonical_buyer_memory,
                conversation_state={
                    "conversation_mode": conversation_mode,
                    "intent_score": intent_result.get("score"),
                    "heat_score": user_memory.get("heat_score"),
                    "buyer_tier": intent_result.get("tier"),
                    "user_value_tier": user_value_tier,
                    "conversation_streak": conversation_streak,
                    "engagement_depth_score": engagement_depth_score,
                },
                emotional_presence_profile=(
                    emotional_presence_profile
                ),
                premium_conversation_continuity_profile=(
                    premium_conversation_continuity_profile
                ),
                whale_burnout_profile=(
                    whale_burnout_profile
                ),
                emotional_dependency_profile=(
                    emotional_dependency_profile
                ),
            )
        )

        self.logger.info(
            f"[3D.20.7 LONG-TERM EMOTIONAL STABILITY] "
            f"{long_term_stability_profile}"
        )

        # 7. Working memory
        working_memory = {
            **user_memory,
            "message_count": message_count,
            "price_questions_count": price_questions_count,
            "exclusive_interest_count": (
                exclusive_interest_count
            ),
            "closing_questions_count": (
                closing_questions_count
            ),
            "offers_shown_count": offers_shown_count,
            "buyer_tier": intent_result["tier"],
            "intent_score": intent_result["score"],
            "message_score": intent_result["message_score"],
            "behavior_score": intent_result["behavior_score"],
            "intent_signals": (
                list(normalized_signals)
                if normalized_signals
                else []
            ),
            "conversation_mode": conversation_mode,
            "active_persona": self.settings.DEFAULT_PERSONA,
            "creator_profile": creator_profile,
            "creator_profile_id": creator_profile.get("id"),
            "last_user_message": message,
            "user_value_tier": user_value_tier,
            "is_whale": is_whale,
            "user_type": user_type,
            "value_score": value_score,
            "attention_tier": attention_tier,
            "effort_mode": effort_mode,
            "timewaster_flags": (
                list(timewaster_flags)
                if timewaster_flags
                else []
            ),
            "customer_value_attention": value_attention_mapping,
            "current_route": effective_route,
            "last_route": effective_route,
            "last_route_confidence": route_confidence,
            "last_route_reason": route_reason,
            "last_route_signals": (
                list(route_signals)
                if route_signals
                else []
            ),
            "route_history": route_history,
            "silent_buyer_score": silent_buyer_score,
            "silent_buyer_tier": silent_buyer_tier,
            "subscriber_profile": subscriber_profile,
            "subscriber_profile_reason": (
                subscriber_profile_reason
            ),
            "engagement_depth_score": engagement_depth_score,
            "conversation_streak": conversation_streak,
            "engagement_tier": engagement_tier,
            "subscriber_engagement_mode": (
                subscriber_engagement_mode
            ),
            "last_offer_content_tag": user_memory.get(
                "last_offer_content_tag"
            ),
            "last_content_tag": user_memory.get(
                "last_offer_content_tag"
            ),
            "behavior_config": behavior_config,
            "gpt_classifier_result": gpt_classifier_result,
                        "explicit_vs_buying_profile": (
                explicit_vs_buying_profile
            ),
            "sexual_engagement_only": (
                explicit_vs_buying_profile.get(
                    "sexual_engagement_only"
                )
            ),
            "monetization_intent": (
                explicit_vs_buying_profile.get(
                    "monetization_intent"
                )
            ),
            "suppress_sales_pressure": (
                explicit_vs_buying_profile.get(
                    "suppress_sales_pressure"
                )
            ),
            "premium_freshness_state": (
                intimacy_overrides.get(
                    "premium_freshness_state"
                )
            ),
            "monetization_freshness_days": (
                intimacy_overrides.get(
                    "monetization_freshness_days"
                )
            ),
            "dormant_whale": (
                intimacy_overrides.get(
                    "dormant_whale"
                )
            ),
            "whale_reactivation_mode": (
                intimacy_overrides.get(
                    "whale_reactivation_mode"
                )
            ),
            "reactivation_strategy": (
                "whale_rewarm"
                if intimacy_overrides.get(
                    "whale_reactivation_mode"
                )
                else "normal"
            ),
            "has_objection": objection_result.get(
                "has_objection",
                False,
            ),
            "objection_type": objection_result.get(
                "objection_type",
                "none",
            ),
            "objection_confidence": objection_result.get(
                "confidence",
                0.0,
            ),
            "response_strategy": behavior.get(
                "response_strategy"
            ),
            "pressure_level": behavior.get(
                "pressure_level"
            ),
            "tone_mode": behavior.get("tone_mode"),
            "should_sell": behavior.get("should_sell"),
            "should_send_offer_behavior": behavior.get(
                "should_send_offer"
            ),
            "should_handle_objection": behavior.get(
                "should_handle_objection"
            ),
            "should_downgrade_effort": behavior.get(
                "should_downgrade_effort"
            ),
            "behavior_notes": behavior.get("behavior_notes"),
            "emotional_rewarm_mode": (
                intimacy_overrides.get(
                    "whale_reactivation_mode"
                )
            ),
            "intimacy_overrides": intimacy_overrides,
            "smooth_escalation_profile": (
                smooth_escalation_profile
            ),
            "smooth_escalation_instruction": (
                smooth_escalation_profile.get("gpt_instruction")
            ),
            "escalation_stage": smooth_escalation_profile.get(
                "escalation_stage"
            ),
            "max_intimacy_intensity": (
                smooth_escalation_profile.get(
                    "max_intimacy_intensity"
                )
            ),
            "explicit_jump_blocked": (
                smooth_escalation_profile.get(
                    "explicit_jump_blocked"
                )
            ),

            # 3D.17.6 runtime orchestration
            "runtime_injection": runtime_injection,
            "runtime_response_strategy": (
                runtime_response_strategy
            ),
            "runtime_escalation_level": (
                runtime_escalation_level
            ),
            "runtime_retention_mode": (
                runtime_retention_mode
            ),
            "runtime_ppv_energy": runtime_ppv_energy,
            "runtime_emotional_continuation": (
                runtime_emotional_continuation
            ),
            "runtime_followup_behavior": (
                runtime_followup_behavior
            ),
            "runtime_premium_routing": (
                runtime_premium_routing
            ),
            "runtime_cooldown_sensitivity": (
                runtime_cooldown_sensitivity
            ),
            "runtime_suppression_handling": (
                runtime_suppression_handling
            ),
            "whale_retention_profile": whale_retention_profile,
            "whale_retention_mode": whale_retention_profile.get(
                "whale_retention_mode"
            ),
            "premium_attention_priority": whale_retention_profile.get(
                "premium_attention_priority"
            ),
            "reduce_sales_pressure": whale_retention_profile.get(
                "reduce_sales_pressure"
            ),
            "emotional_priority_level": whale_retention_profile.get(
                "emotional_priority_level"
            ),
            "relationship_first_response": whale_retention_profile.get(
                "relationship_first_response"
            ),
            "premium_pacing_preference": whale_retention_profile.get(
                "premium_pacing_preference"
            ),
            "whale_retention_instruction": whale_retention_profile.get(
                "gpt_instruction"
            ),
            "premium_relationship_memory_profile": (
                premium_relationship_memory_profile
            ),
            "premium_relationship_memory_active": (
                premium_relationship_memory_profile.get(
                    "premium_relationship_memory_active"
                )
            ),
            "emotional_familiarity_level": (
                premium_relationship_memory_profile.get(
                    "emotional_familiarity_level"
                )
            ),
            "remembered_dynamic_style": (
                premium_relationship_memory_profile.get(
                    "remembered_dynamic_style"
                )
            ),
            "intimacy_continuity_strength": (
                premium_relationship_memory_profile.get(
                    "intimacy_continuity_strength"
                )
            ),
            "relationship_attachment_mode": (
                premium_relationship_memory_profile.get(
                    "relationship_attachment_mode"
                )
            ),
            "premium_memory_priority": (
                premium_relationship_memory_profile.get(
                    "premium_memory_priority"
                )
            ),
            "emotional_callback_candidates": (
                premium_relationship_memory_profile.get(
                    "emotional_callback_candidates"
                )
            ),
            "emotional_presence_bias": (
                premium_relationship_memory_profile.get(
                    "emotional_presence_bias"
                )
            ),
            "continuity_reinforcement_mode": (
                premium_relationship_memory_profile.get(
                    "continuity_reinforcement_mode"
                )
            ),
            "premium_relationship_memory_instruction": (
                premium_relationship_memory_profile.get(
                    "gpt_instruction"
                )
            ),
            # 3D.20.3 — Emotional Presence Refinement
            "emotional_presence_profile": emotional_presence_profile,
            "emotional_presence_active": emotional_presence_profile.get(
                "emotional_presence_active"
            ),
            "emotional_presence_mode": emotional_presence_profile.get(
                "emotional_presence_mode"
            ),
            "emotional_warmth_level": emotional_presence_profile.get(
                "emotional_warmth_level"
            ),
            "validation_intensity": emotional_presence_profile.get(
                "validation_intensity"
            ),
            "tease_softening_level": emotional_presence_profile.get(
                "tease_softening_level"
            ),
            "affection_bias": emotional_presence_profile.get(
                "affection_bias"
            ),
            "pacing_style": emotional_presence_profile.get(
                "pacing_style"
            ),
            "emotional_rhythm_style": emotional_presence_profile.get(
                "emotional_rhythm_style"
            ),
            "immersion_priority": emotional_presence_profile.get(
                "immersion_priority"
            ),
            "emotional_variation_mode": emotional_presence_profile.get(
                "emotional_variation_mode"
            ),
            "escalation_softness": emotional_presence_profile.get(
                "escalation_softness"
            ),
            "response_presence_bias": emotional_presence_profile.get(
                "response_presence_bias"
            ),
            "emotional_presence_instruction": emotional_presence_profile.get(
                "gpt_instruction"
            ),
            # 3D.20.4 — Premium Conversation Continuity
            "premium_conversation_continuity_profile": (
                premium_conversation_continuity_profile
            ),
            "premium_continuity_active": (
                premium_conversation_continuity_profile.get(
                    "premium_continuity_active"
                )
            ),
            "continuity_mode": (
                premium_conversation_continuity_profile.get(
                    "continuity_mode"
                )
            ),
            "emotional_trajectory_state": (
                premium_conversation_continuity_profile.get(
                    "emotional_trajectory_state"
                )
            ),
            "pacing_continuity_bias": (
                premium_conversation_continuity_profile.get(
                    "pacing_continuity_bias"
                )
            ),
            "escalation_transition_style": (
                premium_conversation_continuity_profile.get(
                    "escalation_transition_style"
                )
            ),
            "continuity_cta_suppression": (
                premium_conversation_continuity_profile.get(
                    "continuity_cta_suppression"
                )
            ),
            "relationship_progression_mode": (
                premium_conversation_continuity_profile.get(
                    "relationship_progression_mode"
                )
            ),
            "continuity_memory_weight": (
                premium_conversation_continuity_profile.get(
                    "continuity_memory_weight"
                )
            ),
            "emotional_consistency_bias": (
                premium_conversation_continuity_profile.get(
                    "emotional_consistency_bias"
                )
            ),
            "immersion_continuity_priority": (
                premium_conversation_continuity_profile.get(
                    "immersion_continuity_priority"
                )
            ),
            "response_transition_style": (
                premium_conversation_continuity_profile.get(
                    "response_transition_style"
                )
            ),
            "premium_conversation_continuity_instruction": (
                premium_conversation_continuity_profile.get(
                    "gpt_instruction"
                )
            ),
            # 3D.20.5 — Whale Burnout Prevention
            "whale_burnout_profile": whale_burnout_profile,
            "whale_burnout_prevention_active": (
                whale_burnout_profile.get(
                    "whale_burnout_prevention_active"
                )
            ),
            "burnout_risk": whale_burnout_profile.get(
                "burnout_risk"
            ),
            "monetization_fatigue_level": whale_burnout_profile.get(
                "monetization_fatigue_level"
            ),
            "emotional_fatigue_level": whale_burnout_profile.get(
                "emotional_fatigue_level"
            ),
            "cta_fatigue_level": whale_burnout_profile.get(
                "cta_fatigue_level"
            ),
            "pacing_slowdown_required": whale_burnout_profile.get(
                "pacing_slowdown_required"
            ),
            "soft_presence_mode": whale_burnout_profile.get(
                "soft_presence_mode"
            ),
            "emotional_recovery_mode": whale_burnout_profile.get(
                "emotional_recovery_mode"
            ),
            "offer_pressure_reduction": whale_burnout_profile.get(
                "offer_pressure_reduction"
            ),
            "immersion_recovery_priority": whale_burnout_profile.get(
                "immersion_recovery_priority"
            ),
            "recommended_next_energy": whale_burnout_profile.get(
                "recommended_next_energy"
            ),
            "burnout_safe_response_bias": whale_burnout_profile.get(
                "burnout_safe_response_bias"
            ),
            "whale_burnout_instruction": whale_burnout_profile.get(
                "gpt_instruction"
            ),
             "emotional_dependency_profile": (
                emotional_dependency_profile
            ),
            "dependency_risk_level": (
                emotional_dependency_profile.get(
                    "dependency_risk_level"
                )
            ),
            "dependency_risk_score": (
                emotional_dependency_profile.get(
                    "dependency_risk_score"
                )
            ),
            "over_attachment_escalation": (
                emotional_dependency_profile.get(
                    "over_attachment_escalation"
                )
            ),
            "cling_behavior": (
                emotional_dependency_profile.get(
                    "cling_behavior"
                )
            ),
            "dependency_reinforcement_risk": (
                emotional_dependency_profile.get(
                    "dependency_reinforcement_risk"
                )
            ),
            "emotional_overreliance": (
                emotional_dependency_profile.get(
                    "emotional_overreliance"
                )
            ),
            "excessive_exclusivity_signaling": (
                emotional_dependency_profile.get(
                    "excessive_exclusivity_signaling"
                )
            ),
            "emotional_volatility_escalation": (
                emotional_dependency_profile.get(
                    "emotional_volatility_escalation"
                )
            ),
            "emotional_spacing_bias": (
                emotional_dependency_profile.get(
                    "emotional_spacing_bias"
                )
            ),
            "attachment_stabilization_mode": (
                emotional_dependency_profile.get(
                    "attachment_stabilization_mode"
                )
            ),
            "reinforcement_softening_required": (
                emotional_dependency_profile.get(
                    "reinforcement_softening_required"
                )
            ),
            "emotional_exclusivity_limit": (
                emotional_dependency_profile.get(
                    "emotional_exclusivity_limit"
                )
            ),
            "intimacy_ceiling_state": (
                emotional_dependency_profile.get(
                    "intimacy_ceiling_state"
                )
            ),
            "dependency_safe_response_bias": (
                emotional_dependency_profile.get(
                    "dependency_safe_response_bias"
                )
            ),
            # 3D.20.7 — Long-Term Emotional Stability
            "long_term_stability_profile": (
                long_term_stability_profile
            ),
            "long_term_emotional_stability_active": (
                long_term_stability_profile.get(
                    "long_term_emotional_stability_active"
                )
            ),
            "stability_level": (
                long_term_stability_profile.get(
                    "stability_level"
                )
            ),
            "relationship_rhythm_state": (
                long_term_stability_profile.get(
                    "relationship_rhythm_state"
                )
            ),
            "emotional_volatility_smoothing": (
                long_term_stability_profile.get(
                    "emotional_volatility_smoothing"
                )
            ),
            "emotional_consistency_mode": (
                long_term_stability_profile.get(
                    "emotional_consistency_mode"
                )
            ),
            "anti_whiplash_required": (
                long_term_stability_profile.get(
                    "anti_whiplash_required"
                )
            ),
            "familiarity_preservation_level": (
                long_term_stability_profile.get(
                    "familiarity_preservation_level"
                )
            ),
            "emotional_drift_correction": (
                long_term_stability_profile.get(
                    "emotional_drift_correction"
                )
            ),
            "long_term_response_bias": (
                long_term_stability_profile.get(
                    "long_term_response_bias"
                )
            ),
            "long_term_stability_instruction": (
                long_term_stability_profile.get(
                    "gpt_instruction"
                )
            ),
        }

        # --------------------------------------------------
        # 3D.17.6.5 — RUNTIME BEHAVIOR ENFORCEMENT
        # --------------------------------------------------

        runtime_behavior_result = (
            self.runtime_behavior_enforcement_service
            .apply_runtime_behavior(
                working_memory=working_memory,
                runtime_injection=runtime_injection,
            )
        )

        if runtime_behavior_result.get("success"):
            working_memory = runtime_behavior_result.get(
                "working_memory",
                working_memory,
            )

            self.logger.info(
                f"[3D.17.6.5 RUNTIME ENFORCEMENT] "
                f"{runtime_behavior_result}"
            )

        self.logger.info(
            f"[3D.10.15H INTIMACY OVERRIDES] "
            f"{intimacy_overrides}"
        )
        
        # --------------------------------------------------
        # 3D.17.6.7 — RUNTIME SUPPRESSION ENFORCEMENT
        # --------------------------------------------------

        runtime_suppression_result = (
            self.runtime_suppression_enforcement_service
            .enforce_runtime_suppression(
                working_memory=working_memory,
            )
        )

        if runtime_suppression_result.get(
            "success"
        ):
            working_memory = (
                runtime_suppression_result.get(
                    "working_memory",
                    working_memory,
                )
            )

            self.logger.info(
                f"[3D.17.6.7 SUPPRESSION ENFORCEMENT] "
                f"{runtime_suppression_result}"
            )

        # -----------------------------------------
        # 19H — GPT INTENT TRIGGER ENGINE
        # -----------------------------------------
        classifier = intent_result.get("classifier_result", {}) or {}

        gpt_intent = classifier.get("intent_level")
        gpt_buying = bool(classifier.get("buying_intent", False))
        gpt_close = bool(classifier.get("close_ready", False))
        gpt_action = classifier.get("recommended_action")
        gpt_confident = self._is_gpt_confident(classifier)

        if gpt_confident and gpt_close and gpt_buying:
            print("[19H TRIGGER] HARD CLOSE MODE ACTIVATED")

            conversation_mode = "conversion"
            working_memory["conversation_mode"] = "conversion"
            working_memory["force_offer_now"] = True
            working_memory["pressure_override"] = "high"

        elif gpt_confident and gpt_buying:
            print("[19H TRIGGER] BUYING INTENT MODE")

            conversation_mode = "pre_sell"
            working_memory["conversation_mode"] = "pre_sell"
            working_memory["pressure_override"] = "medium"

        elif gpt_confident and gpt_intent == "medium":
            print("[19H TRIGGER] BUILD TENSION MODE")

            conversation_mode = "tension"
            working_memory["conversation_mode"] = "tension"

        # Persist only existing DB-safe interpreted fields
        interpreted_memory = {
                "intent_score": intent_result["score"],
                "message_score": intent_result["message_score"],
                "behavior_score": intent_result["behavior_score"],
                "intent_signals": list(normalized_signals) if normalized_signals else [],
                "conversation_mode": conversation_mode,
                "active_persona": self.settings.DEFAULT_PERSONA,
                "last_user_message": message,
                "user_type": user_type,
                "value_score": value_score,
                "attention_tier": attention_tier,
                "effort_mode": effort_mode,
                "timewaster_flags": list(timewaster_flags) if timewaster_flags else [],
                "current_route": effective_route,
                "last_route": effective_route,
                "last_route_confidence": route_confidence,
                "last_route_reason": route_reason,
                "last_route_signals": list(route_signals) if route_signals else [],
                "route_history": route_history,
                "silent_buyer_score": silent_buyer_score,
                "silent_buyer_tier": silent_buyer_tier,
                "subscriber_profile": subscriber_profile,
                "subscriber_profile_reason": subscriber_profile_reason,
                "engagement_depth_score": engagement_depth_score,
                "conversation_streak": conversation_streak,
                "engagement_tier": engagement_tier,
                "subscriber_engagement_mode": subscriber_engagement_mode,
        }
        if legacy_commerce_evaluation_allowed:
            interpreted_memory.update({
                "buyer_tier": intent_result["tier"],
                "user_value_tier": user_value_tier,
                "is_whale": is_whale,
            })
        else:
            self.logger.info(
                "event=legacy_memory_mutation_skipped "
                "fields=buyer_tier,user_value_tier,is_whale "
                "memory_source=canonical_commerce"
            )
        self.memory.update_user_memory(user_id, interpreted_memory)

        # 8. Offer logic + timing engine
        if legacy_commerce_evaluation_allowed:
            offer_result = self.offer.determine_offer(
                intent_result["tier"],
                conversation_mode,
                working_memory,
            )
        else:
            offer_result = {
                "offer_type": "none",
                "price": 0,
                "description": "Commerce suppressed by authoritative policy",
            }
            self.logger.info(
                "event=legacy_mutation_skipped operation=offer_determination "
                "policy=%s",
                commerce_execution_policy,
            )

        self.logger.info(f"[OFFER RESULT] {offer_result}")

        # --------------------------------------------------
        # 🔥 15.1 CONTENT GATING
        # --------------------------------------------------

        should_send_content = self.content_gating_service.should_send_content(
            working_memory=working_memory,
            intent_result=intent_result,
            relationship_route=relationship_route,
        )

        selected_content = None
        selected_content_type = None

        if should_send_content:
            selected_content_type = "cms_content_allowed"

            self.logger.info(
                "[15.1 CONTENT GATING] Content allowed. "
                "Selection deferred to ContentService.get_content()."
            )
        # --------------------------------------------------
        # 15.4 STEP 1 — TRACK LAST CONTENT SENT
        # --------------------------------------------------

        if selected_content:
            content_tag = self._cms_content_tag(selected_content) or "unknown"

            working_memory["last_content_sent_tag"] = content_tag
            working_memory["last_content_sent_at"] = datetime.utcnow().isoformat()

            print(f"[15.4 TRACK] tag={content_tag}")

        print(f"[CONTENT DEBUG] should_send={should_send_content} type={selected_content_type}")

        if legacy_commerce_evaluation_allowed:
            timing_result = self.timing.evaluate_timing(
                working_memory,
                intent_result,
            )
        else:
            timing_result = {
                "action": "continue_conversation",
                "send_offer": False,
                "send_nudge": False,
                "wait_hours": 0,
                "reason": "Authoritative Commerce policy suppressed legacy timing.",
                "signals": ["customer_sales_brain_authority"],
            }
            self.logger.info(
                "event=legacy_mutation_skipped operation=offer_timing "
                "policy=%s",
                commerce_execution_policy,
            )

        # ✅ 4B.3 — Subscriber offer timing integration
        subscriber_profile_for_timing = working_memory.get("subscriber_profile", "none")
        behavior_config_for_timing = working_memory.get("behavior_config", {})

        subscriber_pacing_level = behavior_config_for_timing.get("pacing_level", "normal")
        subscriber_pressure_level = behavior_config_for_timing.get("monetization_pressure", "medium")

        if relationship_route == "subscriber" and offer_state not in ["offered", "nudged"]:
            timing_signals = list(timing_result.get("signals", []))

            # NEW_SUBSCRIBER → always warm up first, no early offer
            if subscriber_profile_for_timing == "NEW_SUBSCRIBER":
                timing_result["send_offer"] = False
                timing_result["action"] = "warm_up"
                timing_result["wait_hours"] = max(timing_result.get("wait_hours", 0), 12)
                timing_signals.append("subscriber_new_warmup_delay")
                timing_result["signals"] = timing_signals
                timing_result["reason"] = "New subscriber: delay monetization and warm up first."
                self.logger.info("[SUBSCRIBER TIMING OVERRIDE] new_subscriber_delay_applied")

            # LAPSED_SUBSCRIBER → re-engage before offers
            elif subscriber_profile_for_timing == "LAPSED_SUBSCRIBER":
                timing_result["send_offer"] = False
                timing_result["action"] = "warm_up"
                timing_result["wait_hours"] = max(timing_result.get("wait_hours", 0), 12)
                timing_signals.append("subscriber_lapsed_reengagement_first")
                timing_result["signals"] = timing_signals
                timing_result["reason"] = "Lapsed subscriber: re-engage before monetization."
                self.logger.info("[SUBSCRIBER TIMING OVERRIDE] lapsed_subscriber_reengagement_applied")

            # HIGH_VALUE_SUBSCRIBER → softer pressure, slower pace
            elif (
                subscriber_profile_for_timing == "HIGH_VALUE_SUBSCRIBER"
                and subscriber_pacing_level == "slow"
                and subscriber_pressure_level == "low"
                and timing_result.get("send_offer")
                and intent_result.get("score", 0) < 60
            ):
                timing_result["send_offer"] = False
                timing_result["action"] = "warm_up"
                timing_result["wait_hours"] = max(timing_result.get("wait_hours", 0), 12)
                timing_signals.append("subscriber_high_value_soft_delay")
                timing_result["signals"] = timing_signals
                timing_result["reason"] = "High-value subscriber: slow pacing, delayed monetization."
                self.logger.info("[SUBSCRIBER TIMING OVERRIDE] high_value_soft_delay_applied")

        self.logger.info(
            f"[TIMING] action={timing_result.get('action')} | "
            f"send_offer={timing_result.get('send_offer')} | "
            f"send_nudge={timing_result.get('send_nudge')} | "
            f"wait_hours={timing_result.get('wait_hours')}"
        )
        self.logger.info(f"[TIMING] signals={timing_result.get('signals', [])}")
        self.logger.info(f"[TIMING] reason={timing_result.get('reason', '')}")

        # --------------------------------------------------
        # 🔥 15H-X STEP 1 — BUYER SESSION AUTO-TRIGGER
        # --------------------------------------------------

        hot_result = (
            self.hot_buyer_service.is_hot_buyer(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
                memory={
                    **working_memory,
                    "offer_result": offer_result,
                    "timing_result": timing_result,
                    "last_user_message": message,
                },
            )
            if legacy_commerce_enabled
            else {"is_hot": False, "reason": "authoritative_commerce_policy"}
        )

        self.logger.info(f"[15H-X HOT BUYER CHECK] result={hot_result}")

        should_start_buyer_session = legacy_commerce_enabled and (
            hot_result.get("is_hot")
            or (
                timing_result.get("send_offer") is True
                and offer_result.get("offer_type") not in [None, "none"]
                and route == "sales"
            )
        )

        session_started_this_turn = False
        session_active = bool(user_memory.get("buyer_session_active", False))
        session_cooldown = user_memory.get("buyer_session_cooldown_until")

        if should_start_buyer_session and not session_active and not session_cooldown:
            self.logger.warning(
                "event=legacy_buyer_session_start_blocked "
                "authority=SalesSessionService"
            )

        # --------------------------------------------------
        # 🔥 15H-X STEP 4 — BUYER SESSION STEP ADVANCEMENT
        # --------------------------------------------------

        buyer_session_active_for_step = (
            legacy_commerce_enabled
            and bool(working_memory.get("buyer_session_active", False))
        )
        buyer_session_step = int(working_memory.get("buyer_session_step") or 0)

        if (
            buyer_session_active_for_step
            and buyer_session_step == 1
            and not session_started_this_turn
        ):
            self.logger.info("[15H-X STEP ADVANCE] Step 1 → Step 2")

            self.decision_runtime_boundary.update_memory_fields(
                fanvue_account_id,
                fanvue_user_id,
                {
                    "buyer_session_step": 2,
                    "buyer_session_last_action": "advance_to_step_2",
                },
            )

            working_memory["buyer_session_step"] = 2
            working_memory["buyer_session_last_action"] = "advance_to_step_2"

        # 🔥 7C + 7D — FULL OFFER GATING + TIMING LOGIC

        subscriber_engagement_mode = working_memory.get("subscriber_engagement_mode", "casual")
        engagement_depth_score = working_memory.get("engagement_depth_score", 0)
        conversation_streak = working_memory.get("conversation_streak", 0)
        messages_since_last_offer = working_memory.get("messages_since_last_offer", 0)
        offers_shown_count = working_memory.get("offers_shown_count", 0)
        intent_score = working_memory.get("intent_score", 0)

        send_offer = bool(timing_result.get("send_offer", False))

        # --------------------------------------------------
        # 🔥 15H-X STEP 2 — BUYER SESSION PRIORITY OVERRIDE
        # --------------------------------------------------

        buyer_session_active = (
            legacy_commerce_enabled
            and bool(working_memory.get("buyer_session_active", False))
        )
        buyer_session_step = int(working_memory.get("buyer_session_step") or 0)
        buyer_session_ppv_count = int(working_memory.get("buyer_session_ppv_count") or 0)

        buyer_session_action = None

        if buyer_session_active:
            self.logger.info(
                "[15H-X SESSION OVERRIDE] buyer_session_active=True → suppressing normal offer flow"
            )
            send_offer = False

            if buyer_session_step == 1:
                buyer_session_action = "bridge"

            elif buyer_session_step == 2 and buyer_session_ppv_count == 0:
                buyer_session_action = "prepare_ppv"

        # --------------------------------------------------
        # 15H-X STEP 7 — BUYER SESSION EXIT LOGIC
        # --------------------------------------------------

        if buyer_session_active:
            self.logger.warning(
                "event=legacy_buyer_session_exit_blocked "
                "authority=SalesSessionService"
            )

        # --------------------------------------------------
        # 15H-X STEP 6 — CLOSE / CONVERSION LOGIC
        # --------------------------------------------------

        if buyer_session_active:
            self.logger.warning(
                "event=legacy_buyer_session_close_blocked "
                "authority=CustomerSalesBrainService"
            )

        # 🔥 7F — Soft Transition Detection
        soft_transition = (
            self._should_enter_soft_transition(working_memory)
            if legacy_commerce_enabled
            else False
        )

        # 🔥 7F — Transition → Offer Bridge
        last_message_type = working_memory.get("last_message_type")

        soft_transition_confirmed = (
            last_message_type == "soft_transition"
            and self._is_soft_transition_confirmation(working_memory)
        )

        if not buyer_session_active:
            if soft_transition_confirmed:
                self.logger.info("[SOFT TRANSITION BRIDGE] user_confirmed=True | forcing offer")
                soft_transition = False
                send_offer = True

            elif soft_transition:
                self.logger.info("[SOFT TRANSITION] eligible=True | suppressing immediate offer")
                send_offer = False

            if not soft_transition and (
                subscriber_engagement_mode == "tension" or conversation_mode == "conversion"
            ):
                if intent_score >= 70 and offers_shown_count < 3:
                    send_offer = True

                elif messages_since_last_offer >= 3 and offers_shown_count < 3:
                    if intent_score >= 50:
                        if engagement_depth_score >= 4 and conversation_streak >= 3:
                            send_offer = True

                    elif intent_score >= 20:
                        if engagement_depth_score >= 6 and conversation_streak >= 5:
                            send_offer = True

        # --------------------------------------------------
        # 3D.19.16 — EXPLICIT VS BUYING-INTENT SEPARATION
        # --------------------------------------------------

        if explicit_vs_buying_profile.get(
            "suppress_sales_pressure"
        ):
            self.logger.info(
                "[3D.19.16] Explicit engagement detected "
                "without buying intent → suppressing sales pressure"
            )

            send_offer = False
            soft_transition = False

            if conversation_mode == "conversion":
                conversation_mode = "tension"

            if route == "sales":
                route = "chat"
                effective_route = "chat"

            working_memory["conversation_mode"] = (
                conversation_mode
            )
            working_memory["current_route"] = effective_route
            working_memory["last_route"] = effective_route
            working_memory["send_offer_suppressed_by_3d19_16"] = True
            working_memory["explicit_vs_buying_profile"] = (
                explicit_vs_buying_profile
            )

        # --------------------------------------------------
        # 🔥 15H-X STEP 5 — CONTROLLED PPV PREP
        # --------------------------------------------------

        legacy_offer_requested = bool(send_offer)
        if authoritative_commerce:
            send_offer = presentation_allowed and legacy_offer_requested
            buyer_session_action = None
            self.logger.info(
                "event=legacy_offer_requested requested=%s policy=%s",
                legacy_offer_requested,
                commerce_execution_policy,
            )
            if not send_offer:
                self.logger.info(
                    "event=conversation_continued_without_commerce policy=%s",
                    commerce_execution_policy,
                )

        if legacy_commerce_enabled and buyer_session_action == "prepare_ppv":
            self.logger.info("[15H-X STEP 5] Preparing controlled PPV for buyer session")

            normalized_offer_type = "vip"

            selected_content = self._select_cms_content(
                normalized_offer_type,
                working_memory,
            )

            if selected_content:
                content_tag = self._cms_content_tag(selected_content)

                if (
                    content_tag
                    and self.ownership_decisions.content_tag(
                        fanvue_account_id=fanvue_account_id,
                        fanvue_user_id=fanvue_user_id,
                        content_tag=content_tag,
                    ).blocks_offer
                ):
                    self.logger.info(
                        f"[3D.16 OWNERSHIP BLOCK] buyer-session owned content blocked | "
                        f"account_id={fanvue_account_id} "
                        f"user={fanvue_user_id} "
                        f"tag={content_tag}"
                    )

                    selected_content = None

                    working_memory["ownership_blocked"] = True
                    working_memory["ownership_blocked_tag"] = content_tag
                    working_memory["ownership_blocked_account_id"] = (
                        fanvue_account_id
                    )

            self.logger.info(f"[15H-X STEP 5 SELECTED CONTENT] {selected_content}")

            if selected_content:
                final_offer = {
                    "offer_type": normalized_offer_type,
                    "price": self._cms_content_price(selected_content),
                    "description": "Buyer session controlled VIP offer",
                    "content": selected_content,
                    **self._cms_delivery_payload(selected_content),
                }

                send_offer = True
                soft_transition = False
                working_memory["buyer_session_action"] = "prepare_ppv"

                # --------------------------------------------------
                # 🔥 15H-X STEP 5: SESSION STATE UPDATE
                # --------------------------------------------------

                working_memory["buyer_session_step"] = 3
                working_memory["buyer_session_last_action"] = "ppv_offer_presented"

                current_ppv_count = working_memory.get("buyer_session_ppv_count", 0) or 0
                working_memory["buyer_session_ppv_count"] = current_ppv_count + 1

                self.logger.info("[15H-X STEP 5] Session advanced to step 3")
                self.logger.info(f"[15H-X STEP 5] PPV count: {working_memory['buyer_session_ppv_count']}")

                self.decision_runtime_boundary.update_memory_fields(
                    fanvue_account_id,
                    fanvue_user_id,
                    {
                        "buyer_session_step": working_memory.get("buyer_session_step"),
                        "buyer_session_last_action": working_memory.get("buyer_session_last_action"),
                        "buyer_session_ppv_count": working_memory.get("buyer_session_ppv_count"),
                    },
                )

            else:
                final_offer = {
                    "offer_type": "none",
                    "price": 0,
                    "description": "No matching buyer-session content available",
                    "content": None,
                }

                send_offer = False
                buyer_session_action = "no_content"

        elif legacy_commerce_enabled and send_offer:
            raw_offer_type = offer_result.get("offer_type", "none")
            self.logger.info(f"[SEND OFFER BLOCK ENTERED] raw_offer_type={raw_offer_type}")

            normalized_offer_type = raw_offer_type

            if normalized_offer_type.endswith("_offer"):
                normalized_offer_type = normalized_offer_type.replace("_offer", "")

            # --------------------------------------------------
            # 🔥 15.3 FREE TEASER ROUTING OVERRIDE
            # --------------------------------------------------
            # Medium-intent / curious users should receive TEASE
            # content as a free warmup, not VIP/PREMIUM.
            # High-intent / close-ready users keep paid routing.
            # --------------------------------------------------

            intent_level = gpt_classifier_result.get("intent_level")
            buying_intent = gpt_classifier_result.get("buying_intent")
            close_ready = gpt_classifier_result.get("close_ready")
            recommended_action = gpt_classifier_result.get("recommended_action")

            if (
                intent_level == "medium"
                and not buying_intent
                and not close_ready
                and recommended_action == "build_tension"
            ):
                self.logger.info("[15.3 FREE TEASER ROUTING] medium intent detected → forcing TEASE")
                normalized_offer_type = "tease"

            # --------------------------------------------------
            # 15.4 STEP 2 — DETECT IGNORED CONTENT
            # --------------------------------------------------

            raw_last_tag = (
                working_memory.get("last_offer_content_tag")
                or working_memory.get("last_content_sent_tag")
            )

            last_tag = None

            if raw_last_tag and not str(raw_last_tag).isdigit():
                last_tag = raw_last_tag

            if last_tag:
                # simple detection logic (v1)
                is_positive_signal = (
                    intent_result.get("buying_intent")
                    or intent_result.get("close_ready")
                    or intent_result.get("engagement_level") == "high"
                )

                if not is_positive_signal:
                    working_memory["last_content_outcome"] = "ignored"
                    print(f"[15.4 OUTCOME] tag={last_tag} -> IGNORED")
                else:
                    working_memory["last_content_outcome"] = "positive"
                    print(f"[15.4 OUTCOME] tag={last_tag} -> POSITIVE")

            selected_content = self._select_cms_content(
                normalized_offer_type,
                working_memory,
            )

            if (
                selected_content
                and self._cms_content_offer_type(
                    selected_content,
                    normalized_offer_type,
                )
                == "tease"
            ):
                content_tag = self._cms_content_tag(selected_content)
                working_memory["last_content_sent_tag"] = content_tag
                working_memory["last_content_tag"] = content_tag
                print(f"[15.4 TRACK] stored teaser last_content_sent_tag={content_tag}")

            self.logger.info(f"[SELECTED CONTENT RAW] {selected_content}")

            if selected_content:
                content_item_id = self._cms_content_item_id(selected_content)
                content_tag = self._cms_content_tag(selected_content)

                already_owned = False

                if content_tag:
                    already_owned = (
                        self.ownership_decisions.content_tag(
                            fanvue_account_id=fanvue_account_id,
                            fanvue_user_id=fanvue_user_id,
                            content_tag=content_tag,
                        ).blocks_offer
                    )

                if already_owned:
                    self.logger.info(
                        f"[3D.16 OWNERSHIP BLOCK] owned content blocked | "
                        f"user={fanvue_user_id} tag={content_tag}"
                    )

                    final_offer = {
                        "offer_type": "none",
                        "price": 0,
                        "description": "Content blocked by Ownership Intelligence",
                        "content": None,
                    }

                    working_memory["ownership_blocked"] = True
                    working_memory["ownership_blocked_tag"] = content_tag
                    send_offer = False

                if already_owned:
                    already_seen = True

                else:
                    # --------------------------------------------------
                    # 🔥 DUPLICATE DETECTION (ID + TAG)
                    # --------------------------------------------------

                    already_seen = False

                    if content_item_id:
                        already_seen = self.content_usage_service.has_seen_content(
                            fanvue_account_id=fanvue_account_id,
                            fanvue_user_id=fanvue_user_id,
                            content_item_id=content_item_id,
                        )

                    elif content_tag:
                        already_seen = self.content_usage_service.has_seen_content_tag(
                            fanvue_account_id=fanvue_account_id,
                            fanvue_user_id=fanvue_user_id,
                            content_tag=content_tag,
                        )

                if already_seen and not already_owned:
                    self.logger.info(
                        f"[15.5 DUPLICATE CONTENT DETECTED] tag={content_tag} id={content_item_id}"
                    )

                    replacement_content = None

                    if normalized_offer_type in ["tease", "teaser"] and content_tag:
                        self.logger.info(f"[15.5 TEASER ROTATION] excluding tag={content_tag}")

                        retry_memory = {
                            **working_memory,
                            "last_content_tag": content_tag,
                            "last_content_sent_tag": content_tag,
                            "seen_tags": [content_tag],
                        }

                        replacement_content = self._select_cms_content(
                            normalized_offer_type,
                            retry_memory,
                        )

                        replacement_content_tag = self._cms_content_tag(
                            replacement_content
                        )
                        if replacement_content and replacement_content_tag != content_tag:
                            self.logger.info(
                                f"[15.5 REPLACEMENT SELECTED] old={content_tag} "
                                f"new={replacement_content_tag}"
                            )

                            selected_content = replacement_content
                            content_item_id = self._cms_content_item_id(
                                selected_content
                            )
                            content_tag = replacement_content_tag
                            already_seen = False

                        else:
                            self.logger.info(
                                f"[15.5 NO REPLACEMENT AVAILABLE] blocked_tag={content_tag}"
                            )

                    if already_seen:
                        final_offer = {
                            "offer_type": "none",
                            "price": 0,
                            "description": "Duplicate content blocked by content_usage_log",
                            "content": None,
                        }

                        send_offer = False

                else:
                    is_teaser = normalized_offer_type in ["tease", "teaser"]

                    self.logger.info(
                        f"[CONTENT SELECTED] tag={self._cms_content_tag(selected_content)} | "
                        f"tier={self._cms_content_tier(selected_content)} | "
                        f"type={normalized_offer_type} | "
                        f"price={self._cms_content_price(selected_content)} | "
                        f"deliverable={self._cms_content_deliverable(selected_content)}"
                    )

                    final_offer = {
                        **offer_result,
                        "offer_type": normalized_offer_type,
                        "price": (
                            0
                            if is_teaser
                            else self._cms_content_price(selected_content)
                        ),
                        "content": selected_content,
                        "is_free_teaser": is_teaser,
                        **self._cms_delivery_payload(selected_content),
                    }

                    offer_timestamp = self.offer.get_offer_timestamp()
                    offers_shown_count = self._increment_counter(user_id, "offers_shown_count")

                    self.memory.set_field(user_id, "last_offer_type", final_offer["offer_type"])
                    self.memory.set_field(user_id, "last_offer_timestamp", offer_timestamp)

                    refreshed_memory = self.memory.get_user_memory(user_id)
                    refreshed_memory = self.post_offer.mark_offer_sent(
                        refreshed_memory,
                        final_offer["offer_type"],
                        self._cms_content_tag(selected_content),
                        final_offer.get("price"),
                    )

                    self.memory.update_user_memory(
                        user_id,
                        {
                            "last_offer_timestamp": refreshed_memory.get("last_offer_timestamp"),
                            "last_offer_type": refreshed_memory.get("last_offer_type"),
                            "last_offer_content_tag": refreshed_memory.get("last_offer_content_tag"),
                            "last_offer_price": refreshed_memory.get("last_offer_price"),
                            "post_offer_nudge_count": refreshed_memory.get("post_offer_nudge_count"),
                            "last_nudge_timestamp": refreshed_memory.get("last_nudge_timestamp"),
                            "last_nudge_type": refreshed_memory.get("last_nudge_type"),
                            "offer_state": refreshed_memory.get("offer_state"),
                            "messages_since_last_offer": refreshed_memory.get("messages_since_last_offer"),
                        },
                    )

                    # --------------------------------------------------
                    # 🔥 LOG CONTENT USAGE (ONLY FOR DB CONTENT)
                    # --------------------------------------------------

                    if content_item_id:
                        self.content_usage_service.mark_content_seen(
                            fanvue_account_id=fanvue_account_id,
                            fanvue_user_id=fanvue_user_id,
                            content_item_id=content_item_id,
                            send_source="chat_teaser" if is_teaser else "chat_ppv",
                            caption_used=self._cms_content_caption(
                                selected_content
                            ),
                            price=final_offer.get("price"),
                            usage_type="send",
                            pipeline="decision_engine",
                            classification=content_tag or normalized_offer_type.upper(),
                        )
                    else:
                        self.logger.info(
                            f"[15.3 SKIP LOGGING - NO DB ID] tag={content_tag}"
                        )

            else:
                final_offer = {
                    "offer_type": "none",
                    "price": 0,
                    "description": "No matching content available",
                    "content": None,
                }
                send_offer = False

        else:
            final_offer = {
                "offer_type": "none",
                "price": 0,
                "description": (
                    "Legacy offer suppressed by authoritative Commerce policy"
                    if authoritative_commerce
                    else "Offer suppressed by timing engine"
                ),
                "content": None,
            }

        # ==================================================
        # 3D.20.7.5 — Runtime Compatibility Validation
        # ==================================================

        runtime_compatibility_result = (
            self.runtime_relationship_compatibility_service
            .validate_runtime_compatibility(
                {
                    **working_memory,
                    "send_offer": send_offer,
                    "runtime_mode": (
                        intimacy_overrides.get("runtime_mode")
                    ),
                    "adult_generation_allowed": (
                        intimacy_overrides.get(
                            "adult_generation_allowed"
                        )
                    ),
                    "premium_sexting_allowed": (
                        intimacy_overrides.get(
                            "premium_sexting_allowed"
                        )
                    ),
                    "explicit_allowed": (
                        intimacy_overrides.get(
                            "explicit_allowed"
                        )
                    ),
                }
            )
        )

        # ==================================================
        # 3D.20.8 — Relationship Recovery Logic
        # ==================================================

        relationship_recovery_result = (
            self.relationship_recovery_service
            .build_recovery_profile(
                buyer_memory=working_memory,
                conversation_state=working_memory,
                long_term_stability_profile=working_memory,
                burnout_profile=working_memory,
            )
        )

        working_memory.update(
            relationship_recovery_result
        )

        self.logger.info(
            f"[3D.20.8 RELATIONSHIP RECOVERY] "
            f"{relationship_recovery_result}"
        )

        working_memory.update(
            runtime_compatibility_result
        )

        self.logger.info(
            f"[3D.20.7.5 RUNTIME COMPATIBILITY] "
            f"{runtime_compatibility_result}"
        )

        # ==================================================
        # 3D.20.9 — Advanced Intimacy Governance
        # ==================================================

        advanced_intimacy_governance_result = (
            self.advanced_intimacy_governance_service
            .build_governance_profile(
                runtime_state=working_memory,
            )
        )

        working_memory.update(
            advanced_intimacy_governance_result
        )

        self.logger.info(
            f"[3D.20.9 ADVANCED INTIMACY GOVERNANCE] "
            f"{advanced_intimacy_governance_result}"
        )

        # ==================================================
        # 3D.20.10 — Final Relationship Intelligence Integration
        # ==================================================

        final_relationship_intelligence_result = (
            self.final_relationship_intelligence_service
            .build_final_relationship_profile(
                runtime_state=working_memory,
            )
        )

        working_memory.update(
            final_relationship_intelligence_result
        )

        self.logger.info(
            f"[3D.20.10 FINAL RELATIONSHIP INTELLIGENCE] "
            f"{final_relationship_intelligence_result}"
        )

        # 9. Memory after offer
        updated_memory = self.memory.get_user_memory(user_id)

        nudge_payload = {
            "send_nudge": nudge_allowed,
            "nudge_type": (
                "purchase_intent_follow_up" if nudge_allowed else None
            ),
            "customer_value_attention": value_attention_mapping,
        }

        if legacy_commerce_enabled:
            updated_memory = self.post_offer.increment_post_offer_message_count(
                updated_memory
            )
            updated_memory = self.post_offer.expire_offer_if_needed(
                updated_memory
            )

            if not send_offer and not buyer_session_active:
                nudge_payload = self.post_offer.build_nudge_payload(
                    updated_memory,
                    message,
                    classifier_result=gpt_classifier_result,
                )

                if nudge_payload.get("send_nudge"):
                    self.logger.info(
                        "Legacy nudge triggered: %s",
                        nudge_payload.get("nudge_type"),
                    )
                    updated_memory = self.post_offer.apply_nudge_update(
                        updated_memory, nudge_payload
                    )

            self.memory.update_user_memory(
                user_id,
                {
                    "offer_state": updated_memory.get("offer_state"),
                    "post_offer_nudge_count": updated_memory.get(
                        "post_offer_nudge_count"
                    ),
                    "last_nudge_timestamp": updated_memory.get(
                        "last_nudge_timestamp"
                    ),
                    "last_nudge_type": updated_memory.get("last_nudge_type"),
                    "messages_since_last_offer": updated_memory.get(
                        "messages_since_last_offer"
                    ),
                },
            )
        else:
            self.logger.info(
                "event=legacy_mutation_skipped operation=post_offer_lifecycle "
                "policy=%s",
                commerce_execution_policy,
            )
            if nudge_allowed:
                self.logger.info("event=purchase_intent_reused action=nudge")
            if acknowledgement_allowed:
                self.logger.info(
                    "event=acknowledgement_workflow_selected"
                )

        # --------------------------------------------------
        # 19E — GPT-BASED CONTENT OUTCOME DETECTION
        # --------------------------------------------------

        content_outcome = None
        gpt_result = working_memory.get("gpt_classifier_result", {}) or {}

        user_state = gpt_result.get("user_state")
        recommended_action = gpt_result.get("recommended_action")

        if not self._is_gpt_confident(gpt_result):
            self.logger.warning(
                "[19F SAFETY] Low GPT confidence → skipping content outcome classification"
            )

        else:
            if user_state in ["ready_to_buy", "converted"] or recommended_action in ["close", "offer"]:
                content_outcome = "success"

            elif user_state in ["rejecting", "hesitant"] or recommended_action == "exit":
                content_outcome = "ignored"

        if content_outcome and legacy_commerce_enabled:
            update_payload = {
                "last_content_outcome": content_outcome,
            }

            current_intensity = updated_memory.get("preferred_intensity_score") or 5

            if content_outcome == "success":
                update_payload["content_success_count"] = (
                    (updated_memory.get("content_success_count") or 0) + 1
                )
                update_payload["preferred_intensity_score"] = min(current_intensity + 1, 10)

            elif content_outcome == "ignored":
                update_payload["content_ignore_count"] = (
                    (updated_memory.get("content_ignore_count") or 0) + 1
                )
                update_payload["preferred_intensity_score"] = max(current_intensity - 1, 1)

            self.memory.update_user_memory(user_id, update_payload)

            self.logger.info(
                f"[19E GPT CONTENT OUTCOME] outcome={content_outcome} | payload={update_payload}"
            )

        working_memory_after_offer = {
            **updated_memory,
            "message_count": message_count,
            "buyer_tier": intent_result["tier"],
            "intent_score": intent_result["score"],
            "conversation_mode": conversation_mode,
            "last_user_message": message,
            "intent_signals": (
                list(normalized_signals)
                if normalized_signals
                else []
            ),
            "user_value_tier": user_value_tier,
            "is_whale": is_whale,
            "user_type": user_type,
            "value_score": value_score,
            "attention_tier": attention_tier,
            "effort_mode": effort_mode,
            "timewaster_flags": (
                list(timewaster_flags)
                if timewaster_flags
                else []
            ),
            "customer_value_attention": value_attention_mapping,
            "current_route": effective_route,
            "last_route": effective_route,
            "last_route_confidence": route_confidence,
            "last_route_reason": route_reason,
            "last_route_signals": (
                list(route_signals)
                if route_signals
                else []
            ),
            "route_history": route_history,
            "send_nudge": nudge_payload.get("send_nudge", False),
            "nudge_type": nudge_payload.get("nudge_type"),
            "silent_buyer_score": silent_buyer_score,
            "silent_buyer_tier": silent_buyer_tier,
            "behavior_config": behavior_config,
            "gpt_classifier_result": gpt_classifier_result,
            "subscriber_profile": subscriber_profile,
            "subscriber_profile_reason": (
                subscriber_profile_reason
            ),
            "engagement_depth_score": engagement_depth_score,
            "conversation_streak": conversation_streak,
            "engagement_tier": engagement_tier,
            "subscriber_engagement_mode": (
                subscriber_engagement_mode
            ),
            "final_offer": final_offer,
            "selected_content": final_offer.get("content"),
            "soft_transition": soft_transition,
                        "explicit_vs_buying_profile": (
                explicit_vs_buying_profile
            ),
            "sexual_engagement_only": (
                explicit_vs_buying_profile.get(
                    "sexual_engagement_only"
                )
            ),
            "monetization_intent": (
                explicit_vs_buying_profile.get(
                    "monetization_intent"
                )
            ),
            "suppress_sales_pressure": (
                explicit_vs_buying_profile.get(
                    "suppress_sales_pressure"
                )
            ),
            "offer_price": final_offer.get("price"),
            "offer_link": (
                self._compat_content_link(final_offer.get("content"))
            ),
            "offer_caption": (
                self._cms_content_caption(final_offer.get("content"))
            ),
            "buyer_session_active": (
                working_memory.get("buyer_session_active")
                if legacy_commerce_enabled else False
            ),
            "customer_value_attention": value_attention_mapping,
            "buyer_session_step": (
                working_memory.get("buyer_session_step")
                if legacy_commerce_enabled else None
            ),
            "buyer_session_last_action": (
                working_memory.get("buyer_session_last_action")
                if legacy_commerce_enabled else None
            ),
            "buyer_session_ppv_count": (
                working_memory.get("buyer_session_ppv_count")
                if legacy_commerce_enabled else 0
            ),
            "buyer_session_action": buyer_session_action,

            # 3D.17.6.6 GPT runtime context propagation
            "runtime_injection": runtime_injection,
            "runtime_behavior_result": runtime_behavior_result,

            "runtime_response_strategy": working_memory.get(
                "runtime_response_strategy"
            ),
            "runtime_escalation_level": working_memory.get(
                "runtime_escalation_level"
            ),
            "runtime_retention_mode": working_memory.get(
                "runtime_retention_mode"
            ),
            "runtime_ppv_energy": working_memory.get(
                "runtime_ppv_energy"
            ),
            "runtime_emotional_continuation": working_memory.get(
                "runtime_emotional_continuation"
            ),
            "runtime_followup_behavior": working_memory.get(
                "runtime_followup_behavior"
            ),
            "runtime_premium_routing": working_memory.get(
                "runtime_premium_routing"
            ),
            "runtime_cooldown_sensitivity": working_memory.get(
                "runtime_cooldown_sensitivity"
            ),
            "runtime_suppression_handling": working_memory.get(
                "runtime_suppression_handling"
            ),
            "whale_retention_profile": whale_retention_profile,
            "whale_retention_mode": whale_retention_profile.get(
                "whale_retention_mode"
            ),
            "premium_attention_priority": whale_retention_profile.get(
                "premium_attention_priority"
            ),
            "reduce_sales_pressure": whale_retention_profile.get(
                "reduce_sales_pressure"
            ),
            "emotional_priority_level": whale_retention_profile.get(
                "emotional_priority_level"
            ),
            "relationship_first_response": whale_retention_profile.get(
                "relationship_first_response"
            ),
            "premium_pacing_preference": whale_retention_profile.get(
                "premium_pacing_preference"
            ),
            "whale_retention_instruction": whale_retention_profile.get(
                "gpt_instruction"
            ),
            "premium_relationship_memory_profile": (
                premium_relationship_memory_profile
            ),
            "premium_relationship_memory_active": (
                premium_relationship_memory_profile.get(
                    "premium_relationship_memory_active"
                )
            ),
            "emotional_familiarity_level": (
                premium_relationship_memory_profile.get(
                    "emotional_familiarity_level"
                )
            ),
            "remembered_dynamic_style": (
                premium_relationship_memory_profile.get(
                    "remembered_dynamic_style"
                )
            ),
            "intimacy_continuity_strength": (
                premium_relationship_memory_profile.get(
                    "intimacy_continuity_strength"
                )
            ),
            "relationship_attachment_mode": (
                premium_relationship_memory_profile.get(
                    "relationship_attachment_mode"
                )
            ),
            "premium_memory_priority": (
                premium_relationship_memory_profile.get(
                    "premium_memory_priority"
                )
            ),
            "emotional_callback_candidates": (
                premium_relationship_memory_profile.get(
                    "emotional_callback_candidates"
                )
            ),
            "emotional_presence_bias": (
                premium_relationship_memory_profile.get(
                    "emotional_presence_bias"
                )
            ),
            "continuity_reinforcement_mode": (
                premium_relationship_memory_profile.get(
                    "continuity_reinforcement_mode"
                )
            ),
            "premium_relationship_memory_instruction": (
                premium_relationship_memory_profile.get(
                    "gpt_instruction"
                )
            ),
            # 3D.20.3 — Emotional Presence Refinement
            "emotional_presence_profile": emotional_presence_profile,
            "emotional_presence_active": emotional_presence_profile.get(
                "emotional_presence_active"
            ),
            "emotional_presence_mode": emotional_presence_profile.get(
                "emotional_presence_mode"
            ),
            "emotional_warmth_level": emotional_presence_profile.get(
                "emotional_warmth_level"
            ),
            "validation_intensity": emotional_presence_profile.get(
                "validation_intensity"
            ),
            "tease_softening_level": emotional_presence_profile.get(
                "tease_softening_level"
            ),
            "affection_bias": emotional_presence_profile.get(
                "affection_bias"
            ),
            "pacing_style": emotional_presence_profile.get(
                "pacing_style"
            ),
            "emotional_rhythm_style": emotional_presence_profile.get(
                "emotional_rhythm_style"
            ),
            "immersion_priority": emotional_presence_profile.get(
                "immersion_priority"
            ),
            "emotional_variation_mode": emotional_presence_profile.get(
                "emotional_variation_mode"
            ),
            "escalation_softness": emotional_presence_profile.get(
                "escalation_softness"
            ),
            "response_presence_bias": emotional_presence_profile.get(
                "response_presence_bias"
            ),
            "emotional_presence_instruction": emotional_presence_profile.get(
                "gpt_instruction"
            ),
            # 3D.20.4 — Premium Conversation Continuity
            "premium_conversation_continuity_profile": (
                premium_conversation_continuity_profile
            ),
            "premium_continuity_active": (
                premium_conversation_continuity_profile.get(
                    "premium_continuity_active"
                )
            ),
            "continuity_mode": (
                premium_conversation_continuity_profile.get(
                    "continuity_mode"
                )
            ),
            "emotional_trajectory_state": (
                premium_conversation_continuity_profile.get(
                    "emotional_trajectory_state"
                )
            ),
            "pacing_continuity_bias": (
                premium_conversation_continuity_profile.get(
                    "pacing_continuity_bias"
                )
            ),
            "escalation_transition_style": (
                premium_conversation_continuity_profile.get(
                    "escalation_transition_style"
                )
            ),
            "continuity_cta_suppression": (
                premium_conversation_continuity_profile.get(
                    "continuity_cta_suppression"
                )
            ),
            "relationship_progression_mode": (
                premium_conversation_continuity_profile.get(
                    "relationship_progression_mode"
                )
            ),
            "continuity_memory_weight": (
                premium_conversation_continuity_profile.get(
                    "continuity_memory_weight"
                )
            ),
            "emotional_consistency_bias": (
                premium_conversation_continuity_profile.get(
                    "emotional_consistency_bias"
                )
            ),
            "immersion_continuity_priority": (
                premium_conversation_continuity_profile.get(
                    "immersion_continuity_priority"
                )
            ),
            "response_transition_style": (
                premium_conversation_continuity_profile.get(
                    "response_transition_style"
                )
            ),
            "premium_conversation_continuity_instruction": (
                premium_conversation_continuity_profile.get(
                    "gpt_instruction"
                )
            ),
            # 3D.20.5 — Whale Burnout Prevention
            "whale_burnout_profile": whale_burnout_profile,
            "whale_burnout_prevention_active": (
                whale_burnout_profile.get(
                    "whale_burnout_prevention_active"
                )
            ),
            "burnout_risk": whale_burnout_profile.get(
                "burnout_risk"
            ),
            "monetization_fatigue_level": whale_burnout_profile.get(
                "monetization_fatigue_level"
            ),
            "emotional_fatigue_level": whale_burnout_profile.get(
                "emotional_fatigue_level"
            ),
            "cta_fatigue_level": whale_burnout_profile.get(
                "cta_fatigue_level"
            ),
            "pacing_slowdown_required": whale_burnout_profile.get(
                "pacing_slowdown_required"
            ),
            "soft_presence_mode": whale_burnout_profile.get(
                "soft_presence_mode"
            ),
            "emotional_recovery_mode": whale_burnout_profile.get(
                "emotional_recovery_mode"
            ),
            "offer_pressure_reduction": whale_burnout_profile.get(
                "offer_pressure_reduction"
            ),
            "immersion_recovery_priority": whale_burnout_profile.get(
                "immersion_recovery_priority"
            ),
            "recommended_next_energy": whale_burnout_profile.get(
                "recommended_next_energy"
            ),
            "burnout_safe_response_bias": whale_burnout_profile.get(
                "burnout_safe_response_bias"
            ),
            "whale_burnout_instruction": whale_burnout_profile.get(
                "gpt_instruction"
            ),
        }

        offer_copy = (
            self.offer.build_offer_copy(
                self.settings.DEFAULT_PERSONA,
                final_offer,
                working_memory_after_offer,
            )
            if legacy_commerce_enabled
            else ""
        )

        adult_generation_allowed = bool(
            intimacy_overrides.get("adult_generation_allowed")
        )

        premium_sexting_allowed = bool(
            intimacy_overrides.get("premium_sexting_allowed")
        )

        explicit_allowed = bool(
            intimacy_overrides.get("explicit_allowed")
        )

        runtime_mode = (
            intimacy_overrides.get("runtime_mode")
            or "safe_chat"
        )

        buyer_tier = (
            intimacy_overrides.get("buyer_tier")
            or working_memory_after_offer.get("buyer_tier")
            or "NON_BUYER"
        )
        intimacy_entitlement = str(
            intimacy_overrides.get("intimacy_entitlement") or "GATED"
        ).upper()

        explicit_requested = self._explicit_request_detected(
            message, gpt_classifier_result
        )

        premium_qualified = bool(
            premium_sexting_allowed
            and explicit_allowed
            and intimacy_entitlement in ("PREMIUM", "VIP")
        )

        grok_eligible = bool(
            premium_qualified
            and explicit_requested
            and adult_generation_allowed
        )

        selected_provider = (
            "GROK"
            if grok_eligible
            else "OPENAI"
        )

        if grok_eligible:
            provider_reason = (
                "Qualified premium buyer requested adult/explicit generation."
            )
        elif explicit_requested and not premium_qualified:
            provider_reason = (
                "Adult/explicit request detected, but user is not premium-qualified."
            )
        else:
            provider_reason = (
                "Safe or non-explicit message. OpenAI remains active provider."
            )

        provider_preview = {
            "selected_provider": selected_provider,
            "provider": selected_provider,
            "runtime_mode": runtime_mode,
            "buyer_tier": buyer_tier,
            "intimacy_entitlement": intimacy_entitlement,
            "intimacy_entitlement_reason": intimacy_overrides.get(
                "intimacy_entitlement_reason"
            ),
            "intimacy_investment": intimacy_overrides.get(
                "intimacy_investment"
            ),
            "intimacy_investment_inputs": dict(
                intimacy_overrides.get("intimacy_investment_inputs") or {}
            ),
            "canonical_buyer_authority_used": bool(
                intimacy_overrides.get("canonical_buyer_authority_used")
            ),
            "legacy_buyer_memory_authority_used": bool(
                intimacy_overrides.get("legacy_buyer_memory_authority_used")
            ),
            "adult_generation_allowed": adult_generation_allowed,
            "premium_sexting_allowed": premium_sexting_allowed,
            "explicit_allowed": explicit_allowed,
            "explicit_requested": explicit_requested,
            "nsfw_requested": explicit_requested,
            "premium_qualified": premium_qualified,
            "grok_eligible": grok_eligible,
            "reason": provider_reason,
        }

        intimacy_continuation = bool(
            runtime_mode == "premium_intimacy"
            and intimacy_entitlement in ("PREMIUM", "VIP")
            and gpt_classifier_result.get(
                "sexual_engagement",
                False,
            )
            and gpt_classifier_result.get(
                "explicit_without_buying_intent",
                False,
            )
            and not gpt_classifier_result.get(
                "monetization_intent",
                False,
            )
            and not send_offer
        )

        intimacy_strategy = (
            "continue_tension"
            if intimacy_continuation
            else "normal"
        )

        self.logger.info(
            f"[3D.19.15A INTIMACY STRATEGY] "
            f"continuation={intimacy_continuation} | "
            f"strategy={intimacy_strategy}"
        )

        if buyer_session_action == "exit_session":
            response = (
                "Mmm okay 💋 I’ll behave for now… but don’t disappear on me."
            )

            self.logger.info("[15H-X STEP 7] Normal GPT response overridden by EXIT MODE")

        elif buyer_session_action == "close_mode":
            response = (
                "Mmm okay 😈 then don’t overthink it — unlock it now and come back "
                "and tell me exactly what you think after you see it 💋"
            )

            self.logger.info("[15H-X STEP 6] Normal GPT response overridden by CLOSE MODE")

        else:
            try:
                response = self.gpt.generate_response(
                    self.settings.DEFAULT_PERSONA,
                    conversation_mode,
                    message,
                    {
                    **working_memory_after_offer,
                    # ConversationGateway's canonical per-turn context must
                    # reach the actual generation boundary, not diagnostics only.
                    "runtime_injection": runtime_injection,
                    "conversational_memory": runtime_injection.get(
                        "conversational_memory", {}
                    ),
                    "creator_profile": creator_profile,
                    "fanvue_account_id": fanvue_account_id,
                    "fanvue_user_id": fanvue_user_id,
                    "mapped_fanvue_user_id": mapped_fanvue_user_id,

                    # 3D.19.14 true provider execution context
                    "selected_provider": selected_provider,
                    "provider": selected_provider,
                    "provider_preview": provider_preview,
                    "runtime_mode": runtime_mode,
                    "adult_generation_allowed": adult_generation_allowed,
                    "premium_qualified": premium_qualified,
                    "grok_eligible": grok_eligible,
                    "explicit_requested": explicit_requested,
                    "intimacy_entitlement": intimacy_entitlement,
                    "intimacy_entitlement_reason": intimacy_overrides.get(
                        "intimacy_entitlement_reason"
                    ),
                    "intimacy_investment": intimacy_overrides.get(
                        "intimacy_investment"
                    ),
                    "intimacy_investment_inputs": dict(
                        intimacy_overrides.get("intimacy_investment_inputs") or {}
                    ),
                    "canonical_buyer_authority_used": bool(
                        intimacy_overrides.get("canonical_buyer_authority_used")
                    ),
                    "legacy_buyer_memory_authority_used": bool(
                        intimacy_overrides.get("legacy_buyer_memory_authority_used")
                    ),
                    "intimacy_continuation": intimacy_continuation,
                    "intimacy_strategy": intimacy_strategy,

                    "behavior_context": {
                        "response_strategy": behavior.get("response_strategy"),
                        "tone_mode": behavior.get("tone_mode"),
                        "pressure_level": behavior.get("pressure_level"),
                        "should_handle_objection": behavior.get("should_handle_objection"),
                        "should_downgrade_effort": behavior.get("should_downgrade_effort"),
                        "behavior_notes": behavior.get("behavior_notes"),
                        "intimacy_strategy": intimacy_strategy,
                        "intimacy_continuation": intimacy_continuation,
                        "whale_retention_mode": whale_retention_profile.get(
                            "whale_retention_mode"
                        ),
                        "premium_attention_priority": whale_retention_profile.get(
                            "premium_attention_priority"
                        ),
                        "reduce_sales_pressure": whale_retention_profile.get(
                            "reduce_sales_pressure"
                        ),
                        "emotional_priority_level": whale_retention_profile.get(
                            "emotional_priority_level"
                        ),
                        "relationship_first_response": whale_retention_profile.get(
                            "relationship_first_response"
                        ),
                        "premium_pacing_preference": whale_retention_profile.get(
                            "premium_pacing_preference"
                        ),
                        "whale_retention_instruction": whale_retention_profile.get(
                            "gpt_instruction"
                        ),
                        "premium_relationship_memory_active": (
                            premium_relationship_memory_profile.get(
                                "premium_relationship_memory_active"
                            )
                        ),
                        "emotional_familiarity_level": (
                            premium_relationship_memory_profile.get(
                                "emotional_familiarity_level"
                            )
                        ),
                        "remembered_dynamic_style": (
                            premium_relationship_memory_profile.get(
                                "remembered_dynamic_style"
                            )
                        ),
                        "intimacy_continuity_strength": (
                            premium_relationship_memory_profile.get(
                                "intimacy_continuity_strength"
                            )
                        ),
                        "relationship_attachment_mode": (
                            premium_relationship_memory_profile.get(
                                "relationship_attachment_mode"
                            )
                        ),
                        "premium_memory_priority": (
                            premium_relationship_memory_profile.get(
                                "premium_memory_priority"
                            )
                        ),
                        "emotional_presence_bias": (
                            premium_relationship_memory_profile.get(
                                "emotional_presence_bias"
                            )
                        ),
                        "continuity_reinforcement_mode": (
                            premium_relationship_memory_profile.get(
                                "continuity_reinforcement_mode"
                            )
                        ),
                        "premium_relationship_memory_instruction": (
                            premium_relationship_memory_profile.get(
                                "gpt_instruction"
                            )
                        ),
                        # 3D.20.3 — Emotional Presence Refinement
                        "emotional_presence_active": emotional_presence_profile.get(
                            "emotional_presence_active"
                        ),
                        "emotional_presence_mode": emotional_presence_profile.get(
                            "emotional_presence_mode"
                        ),
                        "emotional_warmth_level": emotional_presence_profile.get(
                            "emotional_warmth_level"
                        ),
                        "validation_intensity": emotional_presence_profile.get(
                            "validation_intensity"
                        ),
                        "tease_softening_level": emotional_presence_profile.get(
                            "tease_softening_level"
                        ),
                        "affection_bias": emotional_presence_profile.get(
                            "affection_bias"
                        ),
                        "pacing_style": emotional_presence_profile.get(
                            "pacing_style"
                        ),
                        "emotional_rhythm_style": emotional_presence_profile.get(
                            "emotional_rhythm_style"
                        ),
                        "immersion_priority": emotional_presence_profile.get(
                            "immersion_priority"
                        ),
                        "emotional_variation_mode": emotional_presence_profile.get(
                            "emotional_variation_mode"
                        ),
                        "escalation_softness": emotional_presence_profile.get(
                            "escalation_softness"
                        ),
                        "response_presence_bias": emotional_presence_profile.get(
                            "response_presence_bias"
                        ),
                        "emotional_presence_instruction": emotional_presence_profile.get(
                            "gpt_instruction"
                        ),
                        # 3D.20.4 — Premium Conversation Continuity
                        "premium_continuity_active": (
                            premium_conversation_continuity_profile.get(
                                "premium_continuity_active"
                            )
                        ),
                        "continuity_mode": (
                            premium_conversation_continuity_profile.get(
                                "continuity_mode"
                            )
                        ),
                        "emotional_trajectory_state": (
                            premium_conversation_continuity_profile.get(
                                "emotional_trajectory_state"
                            )
                        ),
                        "pacing_continuity_bias": (
                            premium_conversation_continuity_profile.get(
                                "pacing_continuity_bias"
                            )
                        ),
                        "escalation_transition_style": (
                            premium_conversation_continuity_profile.get(
                                "escalation_transition_style"
                            )
                        ),
                        "continuity_cta_suppression": (
                            premium_conversation_continuity_profile.get(
                                "continuity_cta_suppression"
                            )
                        ),
                        "relationship_progression_mode": (
                            premium_conversation_continuity_profile.get(
                                "relationship_progression_mode"
                            )
                        ),
                        "continuity_memory_weight": (
                            premium_conversation_continuity_profile.get(
                                "continuity_memory_weight"
                            )
                        ),
                        "emotional_consistency_bias": (
                            premium_conversation_continuity_profile.get(
                                "emotional_consistency_bias"
                            )
                        ),
                        "immersion_continuity_priority": (
                            premium_conversation_continuity_profile.get(
                                "immersion_continuity_priority"
                            )
                        ),
                        "response_transition_style": (
                            premium_conversation_continuity_profile.get(
                                "response_transition_style"
                            )
                        ),
                        "premium_conversation_continuity_instruction": (
                            premium_conversation_continuity_profile.get(
                                "gpt_instruction"
                            )
                        ),
                        # 3D.20.5 — Whale Burnout Prevention
                        "whale_burnout_prevention_active": (
                            whale_burnout_profile.get(
                                "whale_burnout_prevention_active"
                            )
                        ),
                        "burnout_risk": whale_burnout_profile.get(
                            "burnout_risk"
                        ),
                        "monetization_fatigue_level": whale_burnout_profile.get(
                            "monetization_fatigue_level"
                        ),
                        "emotional_fatigue_level": whale_burnout_profile.get(
                            "emotional_fatigue_level"
                        ),
                        "cta_fatigue_level": whale_burnout_profile.get(
                            "cta_fatigue_level"
                        ),
                        "pacing_slowdown_required": whale_burnout_profile.get(
                            "pacing_slowdown_required"
                        ),
                        "soft_presence_mode": whale_burnout_profile.get(
                            "soft_presence_mode"
                        ),
                        "emotional_recovery_mode": whale_burnout_profile.get(
                            "emotional_recovery_mode"
                        ),
                        "offer_pressure_reduction": whale_burnout_profile.get(
                            "offer_pressure_reduction"
                        ),
                        "immersion_recovery_priority": whale_burnout_profile.get(
                            "immersion_recovery_priority"
                        ),
                        "recommended_next_energy": whale_burnout_profile.get(
                            "recommended_next_energy"
                        ),
                        "burnout_safe_response_bias": whale_burnout_profile.get(
                            "burnout_safe_response_bias"
                        ),
                        "whale_burnout_instruction": whale_burnout_profile.get(
                            "gpt_instruction"
                        ),
                         "dependency_risk_level": (
                            emotional_dependency_profile.get(
                                "dependency_risk_level"
                            )
                        ),

                        "dependency_risk_score": (
                            emotional_dependency_profile.get(
                                "dependency_risk_score"
                            )
                        ),

                        "over_attachment_escalation": (
                            emotional_dependency_profile.get(
                                "over_attachment_escalation"
                            )
                        ),

                        "cling_behavior": (
                            emotional_dependency_profile.get(
                                "cling_behavior"
                            )
                        ),

                        "dependency_reinforcement_risk": (
                            emotional_dependency_profile.get(
                                "dependency_reinforcement_risk"
                            )
                        ),

                        "emotional_overreliance": (
                            emotional_dependency_profile.get(
                                "emotional_overreliance"
                            )
                        ),

                        "excessive_exclusivity_signaling": (
                            emotional_dependency_profile.get(
                                "excessive_exclusivity_signaling"
                            )
                        ),

                        "emotional_volatility_escalation": (
                            emotional_dependency_profile.get(
                                "emotional_volatility_escalation"
                            )
                        ),

                        "emotional_spacing_bias": (
                            emotional_dependency_profile.get(
                                "emotional_spacing_bias"
                            )
                        ),

                        "attachment_stabilization_mode": (
                            emotional_dependency_profile.get(
                                "attachment_stabilization_mode"
                            )
                        ),

                        "reinforcement_softening_required": (
                            emotional_dependency_profile.get(
                                "reinforcement_softening_required"
                            )
                        ),

                        "emotional_exclusivity_limit": (
                            emotional_dependency_profile.get(
                                "emotional_exclusivity_limit"
                            )
                        ),

                        "intimacy_ceiling_state": (
                            emotional_dependency_profile.get(
                                "intimacy_ceiling_state"
                            )
                        ),

                        "dependency_safe_response_bias": (
                            emotional_dependency_profile.get(
                                "dependency_safe_response_bias"
                            )
                        ),
                        "dependency_guidance": (
                            emotional_dependency_profile.get(
                                "reason"
                            )
                        ),
                    },
                    "reactivation_strategy": (
                        working_memory_after_offer.get(
                            "reactivation_strategy"
                        )
                    ),
                    "emotional_rewarm_mode": (
                        working_memory_after_offer.get(
                            "emotional_rewarm_mode"
                        )
                    ),
                    },
                    send_offer,
                    final_offer,
                    offer_copy,
                    chat_history=chat_history,
                )
            except Exception as error:
                self.logger.exception(
                    "[DECISION ENGINE FINAL GPT ERROR] exception_type=%s "
                    "exception_message=%s",
                    type(error).__name__,
                    str(error),
                )
                raise
            
        self.memory.set_field(user_id, "last_user_message", message)
        self.memory.set_field(user_id, "last_bot_response", response)

        previous_message_type = working_memory_after_offer.get("last_message_type")

        if send_offer:
            self.memory.set_field(user_id, "last_message_type", "normal")
        elif soft_transition:
            self.memory.set_field(user_id, "last_message_type", "soft_transition")
        elif previous_message_type == "soft_transition":
            self.memory.set_field(user_id, "last_message_type", "soft_transition")
        else:
            self.memory.set_field(user_id, "last_message_type", "normal")

        self.memory.increment_outbound_message(user_id)

        self.logger.info(f"Message: {message}")
        self.logger.info(f"Response: {response}")
        self.logger.info(f"[FINAL ROUTE] base={route} | effective={effective_route}")
        self.logger.info(f"[FINAL ROUTE] base={route} | effective={effective_route}")

        # --------------------------------------------------
        # 15.6 FINAL BEHAVIOR DEBUG
        # --------------------------------------------------
        self.logger.info(
            f"[15.6 FINAL] strategy={behavior.get('response_strategy')} | "
            f"tone={behavior.get('tone_mode')} | "
            f"pressure={behavior.get('pressure_level')} | "
            f"downgrade={behavior.get('should_downgrade_effort')}"
        )

        # --------------------------------------------------
        # 🔥 SEND LOG TRACKING
        # --------------------------------------------------

        try:
            self.decision_runtime_boundary.log_send_event(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
                fanvue_user_uuid=str(user_id),

                message_type=working_memory_after_offer.get("last_message_type", "normal"),
                route=effective_route,

                offer_type=(
                    (offer_result or {}).get("offer_type")
                    or (final_offer or {}).get("offer_type")
                ),

                content_tag=(
                    (final_offer or {}).get("content", {}).get("tag")
                    if (final_offer or {}).get("content")
                    else None
                ),

                price=(
                    (final_offer or {}).get("price")
                    or (offer_result or {}).get("price")
                    or 0
                ),

                payload={
                    "message": message,
                    "offer": final_offer,
                    "offer_result": offer_result,
                    "send_offer": send_offer,
                    "delivery_type": (final_offer or {}).get("delivery_type"),
                    "delivery_permission_mode": (
                        (final_offer or {}).get("delivery_permission_mode")
                    ),
                    "delivery_requires_payment": (
                        (final_offer or {}).get("delivery_requires_payment")
                    ),
                    "send_nudge": nudge_payload.get("send_nudge", False),
                    "buyer_session_action": buyer_session_action,
                    "mode": conversation_mode,
                },

                response={
                    "text": response,
                },
            )
        except Exception as e:
            self.logger.error(f"[SEND LOG ERROR] {e}")

        # 🚀 FUTURE: Real Fanvue send
        # return self.fanvue_api.send_chat_message(
        #     user_uuid=fanvue_user_id,
        #     payload=payload,
        # )

        self.logger.info(
            "[3D.17.6 FINAL RUNTIME STATE] "
            f"strategy={runtime_response_strategy} | "
            f"retention={runtime_retention_mode} | "
            f"ppv_energy={runtime_ppv_energy}"
        )

        adult_generation_allowed = bool(
            intimacy_overrides.get("adult_generation_allowed")
        )

        premium_sexting_allowed = bool(
            intimacy_overrides.get("premium_sexting_allowed")
        )

        explicit_allowed = bool(
            intimacy_overrides.get("explicit_allowed")
        )

        runtime_mode = (
            intimacy_overrides.get("runtime_mode")
            or "safe_chat"
        )

        buyer_tier = (
            intimacy_overrides.get("buyer_tier")
            or working_memory_after_offer.get("buyer_tier")
            or "NON_BUYER"
        )

        explicit_requested = self._explicit_request_detected(
            message, gpt_classifier_result
        )

        premium_qualified = bool(
            premium_sexting_allowed
            and explicit_allowed
            and intimacy_entitlement in ("PREMIUM", "VIP")
        )

        grok_eligible = bool(
            premium_qualified
            and explicit_requested
            and adult_generation_allowed
        )

        selected_provider = (
            "GROK"
            if grok_eligible
            else "OPENAI"
        )

        if grok_eligible:
            provider_reason = (
                "Qualified premium buyer requested adult/explicit generation."
            )
        elif explicit_requested and not premium_qualified:
            provider_reason = (
                "Adult/explicit request detected, but user is not premium-qualified."
            )
        else:
            provider_reason = (
                "Safe or non-explicit message. OpenAI remains active provider."
            )

        provider_preview = {
            **provider_preview,
            "selected_provider": selected_provider,
            "provider": selected_provider,
            "runtime_mode": runtime_mode,
            "buyer_tier": buyer_tier,
            "intimacy_entitlement": intimacy_entitlement,
            "intimacy_entitlement_reason": intimacy_overrides.get(
                "intimacy_entitlement_reason"
            ),
            "intimacy_investment": intimacy_overrides.get(
                "intimacy_investment"
            ),
            "intimacy_investment_inputs": dict(
                intimacy_overrides.get("intimacy_investment_inputs") or {}
            ),
            "canonical_buyer_authority_used": bool(
                intimacy_overrides.get("canonical_buyer_authority_used")
            ),
            "legacy_buyer_memory_authority_used": bool(
                intimacy_overrides.get("legacy_buyer_memory_authority_used")
            ),
            "adult_generation_allowed": adult_generation_allowed,
            "premium_sexting_allowed": premium_sexting_allowed,
            "explicit_allowed": explicit_allowed,
            "explicit_requested": explicit_requested,
            "nsfw_requested": explicit_requested,
            "premium_qualified": premium_qualified,
            "grok_eligible": grok_eligible,
            "reason": provider_reason,
        }

        response_text_length = len(response) if isinstance(response, str) else 0
        response_text_preview = response[:100] if isinstance(response, str) else None
        self.logger.info(
            "[DECISION ENGINE RETURN] response_text_length=%s "
            "response_text_preview=%r blocked=%s send_offer=%s "
            "legacy_offer_requested=%s commerce_policy=%s",
            response_text_length,
            response_text_preview,
            False,
            send_offer,
            legacy_offer_requested,
            commerce_execution_policy,
        )

        return self._runtime_decision_result({
            "route": routing_result,
            "relationship_route": relationship_route,
            "effective_route": effective_route,
            "subscriber_profile": subscriber_profile,
            "subscriber_profile_reason": subscriber_profile_reason,
            "intent": intent_result,
            "mode": conversation_mode,
            "offer": final_offer,
            "send_offer": send_offer,
            "legacy_offer_requested": legacy_offer_requested,
            "commerce_execution_policy": commerce_execution_policy,
            "commerce_offer_authorized": presentation_allowed,
            "final_offer_authorized": (
                send_offer and presentation_allowed
                if authoritative_commerce
                else send_offer
            ),
            "commerce_readiness": self._commerce_readiness(
                message,
                gpt_classifier_result,
                explicit_vs_buying_profile,
            ),
            "delivery_type": (final_offer or {}).get("delivery_type"),
            "delivery_permission_mode": (
                (final_offer or {}).get("delivery_permission_mode")
            ),
            "delivery_requires_payment": (
                (final_offer or {}).get("delivery_requires_payment")
            ),
            "send_nudge": nudge_payload.get(
                "send_nudge",
                False,
            ),
            "soft_transition": soft_transition,
            "nudge_type": nudge_payload.get(
                "nudge_type"
            ),
            "response": response,
            "buyer_session_active": (
                working_memory_after_offer.get(
                    "buyer_session_active",
                    False,
                )
            ),
            "buyer_session_step": (
                working_memory_after_offer.get(
                    "buyer_session_step"
                )
            ),
            "buyer_session_last_action": (
                working_memory_after_offer.get(
                    "buyer_session_last_action"
                )
            ),
            "buyer_session_ppv_count": (
                working_memory_after_offer.get(
                    "buyer_session_ppv_count"
                )
            ),
            "buyer_session_action": (
                working_memory_after_offer.get(
                    "buyer_session_action"
                )
            ),
            "runtime_injection": runtime_injection,
            "commerce_decision": runtime_injection.get(
                "commerce_decision"
            ),
            "runtime_suppression_result": (
                runtime_suppression_result
            ),

            # 3D.20.7.5 — Runtime Compatibility Debug
            "runtime_compatibility_result": (
                runtime_compatibility_result
            ),
            "runtime_relationship_compatibility_safe": (
                working_memory.get(
                    "runtime_relationship_compatibility_safe"
                )
            ),
            "runtime_relationship_conflicts": (
                working_memory.get(
                    "runtime_relationship_conflicts"
                )
            ),
            "runtime_relationship_validation_active": (
                working_memory.get(
                    "runtime_relationship_validation_active"
                )
            ),

            # 3D.19 provider / adult-routing debug visibility
            "provider": selected_provider,
            "selected_provider": selected_provider,
            "provider_preview": provider_preview,
            "generation_preview": provider_preview,
            "runtime_mode": runtime_mode,
            "adult_generation_allowed": (
                adult_generation_allowed
            ),
            "premium_sexting_allowed": (
                premium_sexting_allowed
            ),
            "explicit_allowed": explicit_allowed,
            "explicit_requested": explicit_requested,
            "nsfw_requested": explicit_requested,
            "premium_qualified": premium_qualified,
            "grok_eligible": grok_eligible,
            "buyer_tier": buyer_tier,
            "intimacy_overrides": intimacy_overrides,
            "smooth_escalation_profile": (
                smooth_escalation_profile
            ),
            "whale_retention_profile": whale_retention_profile,
            "whale_retention_mode": whale_retention_profile.get(
                "whale_retention_mode"
            ),
            "premium_attention_priority": whale_retention_profile.get(
                "premium_attention_priority"
            ),
            "reduce_sales_pressure": whale_retention_profile.get(
                "reduce_sales_pressure"
            ),
            "emotional_priority_level": whale_retention_profile.get(
                "emotional_priority_level"
            ),
            "relationship_first_response": whale_retention_profile.get(
                "relationship_first_response"
            ),
            "premium_pacing_preference": whale_retention_profile.get(
                "premium_pacing_preference"
            ),
            "premium_relationship_memory_profile": (
                premium_relationship_memory_profile
            ),
            "premium_relationship_memory_active": (
                premium_relationship_memory_profile.get(
                    "premium_relationship_memory_active"
                )
            ),
            "emotional_familiarity_level": (
                premium_relationship_memory_profile.get(
                    "emotional_familiarity_level"
                )
            ),
            "remembered_dynamic_style": (
                premium_relationship_memory_profile.get(
                    "remembered_dynamic_style"
                )
            ),
            "intimacy_continuity_strength": (
                premium_relationship_memory_profile.get(
                    "intimacy_continuity_strength"
                )
            ),
            "relationship_attachment_mode": (
                premium_relationship_memory_profile.get(
                    "relationship_attachment_mode"
                )
            ),
            "premium_memory_priority": (
                premium_relationship_memory_profile.get(
                    "premium_memory_priority"
                )
            ),
            "emotional_presence_bias": (
                premium_relationship_memory_profile.get(
                    "emotional_presence_bias"
                )
            ),
            "continuity_reinforcement_mode": (
                premium_relationship_memory_profile.get(
                    "continuity_reinforcement_mode"
                )
            ),
            # 3D.20.3 — Emotional Presence Refinement
            "emotional_presence_profile": emotional_presence_profile,
            "emotional_presence_active": emotional_presence_profile.get(
                "emotional_presence_active"
            ),
            "emotional_presence_mode": emotional_presence_profile.get(
                "emotional_presence_mode"
            ),
            "emotional_warmth_level": emotional_presence_profile.get(
                "emotional_warmth_level"
            ),
            "validation_intensity": emotional_presence_profile.get(
                "validation_intensity"
            ),
            "tease_softening_level": emotional_presence_profile.get(
                "tease_softening_level"
            ),
            "affection_bias": emotional_presence_profile.get(
                "affection_bias"
            ),
            "pacing_style": emotional_presence_profile.get(
                "pacing_style"
            ),
            "emotional_rhythm_style": emotional_presence_profile.get(
                "emotional_rhythm_style"
            ),
            "immersion_priority": emotional_presence_profile.get(
                "immersion_priority"
            ),
            "emotional_variation_mode": emotional_presence_profile.get(
                "emotional_variation_mode"
            ),
            "escalation_softness": emotional_presence_profile.get(
                "escalation_softness"
            ),
            "response_presence_bias": emotional_presence_profile.get(
                "response_presence_bias"
            ),
            # 3D.20.4 — Premium Conversation Continuity
            "premium_conversation_continuity_profile": (
                premium_conversation_continuity_profile
            ),
            "premium_continuity_active": (
                premium_conversation_continuity_profile.get(
                    "premium_continuity_active"
                )
            ),
            "continuity_mode": (
                premium_conversation_continuity_profile.get(
                    "continuity_mode"
                )
            ),
            "emotional_trajectory_state": (
                premium_conversation_continuity_profile.get(
                    "emotional_trajectory_state"
                )
            ),
            "pacing_continuity_bias": (
                premium_conversation_continuity_profile.get(
                    "pacing_continuity_bias"
                )
            ),
            "escalation_transition_style": (
                premium_conversation_continuity_profile.get(
                    "escalation_transition_style"
                )
            ),
            "continuity_cta_suppression": (
                premium_conversation_continuity_profile.get(
                    "continuity_cta_suppression"
                )
            ),
            "relationship_progression_mode": (
                premium_conversation_continuity_profile.get(
                    "relationship_progression_mode"
                )
            ),
            "continuity_memory_weight": (
                premium_conversation_continuity_profile.get(
                    "continuity_memory_weight"
                )
            ),
            "emotional_consistency_bias": (
                premium_conversation_continuity_profile.get(
                    "emotional_consistency_bias"
                )
            ),
            "immersion_continuity_priority": (
                premium_conversation_continuity_profile.get(
                    "immersion_continuity_priority"
                )
            ),
            "response_transition_style": (
                premium_conversation_continuity_profile.get(
                    "response_transition_style"
                )
            ),
            # 3D.20.5 — Whale Burnout Prevention
            "whale_burnout_profile": whale_burnout_profile,
            "whale_burnout_prevention_active": (
                whale_burnout_profile.get(
                    "whale_burnout_prevention_active"
                )
            ),
            "burnout_risk": whale_burnout_profile.get(
                "burnout_risk"
            ),
            "monetization_fatigue_level": whale_burnout_profile.get(
                "monetization_fatigue_level"
            ),
            "emotional_fatigue_level": whale_burnout_profile.get(
                "emotional_fatigue_level"
            ),
            "cta_fatigue_level": whale_burnout_profile.get(
                "cta_fatigue_level"
            ),
            "pacing_slowdown_required": whale_burnout_profile.get(
                "pacing_slowdown_required"
            ),
            "soft_presence_mode": whale_burnout_profile.get(
                "soft_presence_mode"
            ),
            "emotional_recovery_mode": whale_burnout_profile.get(
                "emotional_recovery_mode"
            ),
            "offer_pressure_reduction": whale_burnout_profile.get(
                "offer_pressure_reduction"
            ),
            "immersion_recovery_priority": whale_burnout_profile.get(
                "immersion_recovery_priority"
            ),
            "recommended_next_energy": whale_burnout_profile.get(
                "recommended_next_energy"
            ),
            "burnout_safe_response_bias": whale_burnout_profile.get(
                "burnout_safe_response_bias"
            ),
              "burnout_safe_response_bias": whale_burnout_profile.get(
                "burnout_safe_response_bias"
            ),

            # 3D.20.6 — Emotional Dependency Safeguards
            "emotional_dependency_profile": (
                emotional_dependency_profile
            ),
            "dependency_risk_level": (
                emotional_dependency_profile.get(
                    "dependency_risk_level"
                )
            ),
            "dependency_risk_score": (
                emotional_dependency_profile.get(
                    "dependency_risk_score"
                )
            ),
            "over_attachment_escalation": (
                emotional_dependency_profile.get(
                    "over_attachment_escalation"
                )
            ),
            "cling_behavior": (
                emotional_dependency_profile.get(
                    "cling_behavior"
                )
            ),
            "dependency_reinforcement_risk": (
                emotional_dependency_profile.get(
                    "dependency_reinforcement_risk"
                )
            ),
            "emotional_overreliance": (
                emotional_dependency_profile.get(
                    "emotional_overreliance"
                )
            ),
            "excessive_exclusivity_signaling": (
                emotional_dependency_profile.get(
                    "excessive_exclusivity_signaling"
                )
            ),
            "emotional_volatility_escalation": (
                emotional_dependency_profile.get(
                    "emotional_volatility_escalation"
                )
            ),
            "emotional_spacing_bias": (
                emotional_dependency_profile.get(
                    "emotional_spacing_bias"
                )
            ),
            "attachment_stabilization_mode": (
                emotional_dependency_profile.get(
                    "attachment_stabilization_mode"
                )
            ),
            "reinforcement_softening_required": (
                emotional_dependency_profile.get(
                    "reinforcement_softening_required"
                )
            ),
            "emotional_exclusivity_limit": (
                emotional_dependency_profile.get(
                    "emotional_exclusivity_limit"
                )
            ),
            "intimacy_ceiling_state": (
                emotional_dependency_profile.get(
                    "intimacy_ceiling_state"
                )
            ),
            "dependency_safe_response_bias": (
                emotional_dependency_profile.get(
                    "dependency_safe_response_bias"
                )
            ),
            # 3D.20.7 — Long-Term Emotional Stability
            "long_term_stability_profile": (
                long_term_stability_profile
            ),
            "long_term_emotional_stability_active": (
                long_term_stability_profile.get(
                    "long_term_emotional_stability_active"
                )
            ),
            "stability_level": (
                long_term_stability_profile.get(
                    "stability_level"
                )
            ),
            "relationship_rhythm_state": (
                long_term_stability_profile.get(
                    "relationship_rhythm_state"
                )
            ),
            "long_term_response_bias": (
                long_term_stability_profile.get(
                    "long_term_response_bias"
                )
            ),
            # 3D.20.8 — Relationship Recovery
            "relationship_recovery_result": (
                relationship_recovery_result
            ),
            "relationship_recovery_active": (
                working_memory.get(
                    "relationship_recovery_active"
                )
            ),
            "recovery_risk": (
                working_memory.get(
                    "recovery_risk"
                )
            ),
            "recovery_mode": (
                working_memory.get(
                    "recovery_mode"
                )
            ),
            "reduce_pressure": (
                working_memory.get(
                    "reduce_pressure"
                )
            ),
            "increase_presence": (
                working_memory.get(
                    "increase_presence"
                )
            ),
            "recovery_cta_suppression": (
                working_memory.get(
                    "recovery_cta_suppression"
                )
            ),
                        "recovery_cta_suppression": (
                working_memory.get(
                    "recovery_cta_suppression"
                )
            ),

            # 3D.20.9 — Advanced Intimacy Governance
            "advanced_intimacy_governance_result": (
                advanced_intimacy_governance_result
            ),
            "advanced_intimacy_governance_active": (
                working_memory.get(
                    "advanced_intimacy_governance_active"
                )
            ),
            "premium_intimacy_allowed": (
                working_memory.get(
                    "premium_intimacy_allowed"
                )
            ),
            "intimacy_escalation_allowed": (
                working_memory.get(
                    "intimacy_escalation_allowed"
                )
            ),
            "intimacy_governance_mode": (
                working_memory.get(
                    "intimacy_governance_mode"
                )
            ),
            "intimacy_escalation_ceiling": (
                working_memory.get(
                    "intimacy_escalation_ceiling"
                )
            ),
                        "governance_reason": (
                working_memory.get(
                    "governance_reason"
                )
            ),

            # 3D.20.10 — Final Relationship Intelligence
            "final_relationship_intelligence_result": (
                final_relationship_intelligence_result
            ),
            "final_relationship_intelligence_active": (
                working_memory.get(
                    "final_relationship_intelligence_active"
                )
            ),
            "relationship_protection_active": (
                working_memory.get(
                    "relationship_protection_active"
                )
            ),
            "master_relationship_mode": (
                working_memory.get(
                    "master_relationship_mode"
                )
            ),
            "relationship_override_active": (
                working_memory.get(
                    "relationship_override_active"
                )
            ),
            "relationship_runtime_summary": (
                working_memory.get(
                    "relationship_runtime_summary"
                )
            ),
            "relationship_behavior_directive": (
                working_memory.get(
                    "relationship_behavior_directive"
                )
            ),
            # 3D.19 provider / adult-routing debug visibility
        })

    @staticmethod
    def _runtime_decision_result(
        decision: dict | None,
    ) -> DecisionEngineResult:
        return DecisionEngineResult.from_mapping(decision)

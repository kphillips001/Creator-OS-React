"""Narrow deterministic pre-first-offer readiness policy."""
from app.models.adaptive_sales_readiness import (
    AdaptiveSalesReadinessConfig, AdaptiveSalesReadinessDecision,
)
from app.repositories.adaptive_sales_readiness_repository import AdaptiveSalesReadinessRepository


class AdaptiveSalesReadinessService:
    def __init__(self, repository=None, direct_intent_detector=None):
        self.repository = repository or AdaptiveSalesReadinessRepository()
        self.direct_intent_detector = direct_intent_detector

    def evaluate(self, *, creator_profile_id, fanvue_account_id, fanvue_user_id,
                 conversation_thread_id, buyer_stage, purchase_count, context):
        policy = self.repository.active_policy(creator_profile_id=creator_profile_id,
                                               fanvue_account_id=fanvue_account_id)
        if not policy:
            return None
        config = AdaptiveSalesReadinessConfig.from_mapping(policy.get("policy_configuration"))
        message = str(context.get("latest_message") or "")
        direct = bool(self.direct_intent_detector and self.direct_intent_detector(message))
        state = dict(context.get("sales_progression") or {})
        phase = str(state.get("phase") or "CONVERSATIONAL").upper()
        snapshot = self.repository.snapshot(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id, conversation_thread_id=conversation_thread_id,
            meaningful_inactivity_days=config.meaningful_inactivity_days)
        depth = int(snapshot.get("warmup_depth") or 0)
        lifetime = int(snapshot.get("lifetime_inbound_depth") or 0)
        segment = ("ACTIVE_SESSION" if context.get("sales_session_id") else
                   "REPEAT_BUYER" if purchase_count > 1 else
                   "FIRST_TIME_BUYER" if purchase_count == 1 else
                   "RETURNING_NON_BUYER" if lifetime > depth and lifetime >= config.normal_prospect_target_min else
                   "PROSPECT")
        position = ("BELOW_BENCHMARK" if depth < config.normal_prospect_target_min else
                    "NORMAL_BENCHMARK" if depth <= config.normal_prospect_target_max else
                    "BEYOND_BENCHMARK")
        teaser = dict(snapshot.get("teaser_response") or {})
        teaser_responded = teaser.get("next_inbound_at") is not None
        continuity = len(tuple(context.get("recent_conversation_requests") or ())) >= 2
        commercial_curiosity = bool(context.get("requested_media_type"))
        healthy_engagement = continuity and len(message.strip()) >= 4
        adjustments = {"buyerHistory": purchase_count > 0,
                       "relationshipHistory": segment == "RETURNING_NON_BUYER",
                       "freeTeaserResponse": teaser_responded}
        evidence = {"warmupDepth": depth, "windowStartedAt": snapshot.get("window_started_at"),
                    "benchmark": {"min": config.normal_prospect_target_min, "max": config.normal_prospect_target_max,
                                  "advisory": True, "automaticOfferAtMaximum": False},
                    "engagement": {"conversationContinuity": continuity, "healthyCurrentEngagement": healthy_engagement,
                                   "commercialCuriosity": commercial_curiosity},
                    "teaserResponse": teaser, "adjustments": adjustments,
                    "countDirection": config.count_direction, "countScope": config.count_scope}
        if context.get("sales_session_id"):
            return AdaptiveSalesReadinessDecision(False, "ACTIVE_SESSION_PRECEDENCE", segment,
                direct, False, depth, position, evidence, {"activeSession": True})
        if phase in {"TEASE", "BUILD_INTEREST"}:
            return AdaptiveSalesReadinessDecision(True, "EXISTING_COMMERCIAL_PROGRESSION", segment,
                direct, True, depth, position, evidence)
        if direct and config.direct_purchase_intent_bypass:
            return AdaptiveSalesReadinessDecision(True, "DIRECT_PURCHASE_INTENT_BYPASS", segment,
                True, True, depth, position, evidence)
        targets = {"PROSPECT": config.normal_prospect_target_min,
                   "RETURNING_NON_BUYER": max(6, config.normal_prospect_target_min - 2),
                   "FIRST_TIME_BUYER": max(5, config.normal_prospect_target_min - 4),
                   "REPEAT_BUYER": max(4, config.normal_prospect_target_min - 6)}
        target = targets.get(segment, config.normal_prospect_target_min)
        strong = healthy_engagement and (commercial_curiosity or teaser_responded or depth >= target)
        authorized = depth >= target and strong
        reason = ("ADAPTIVE_READINESS_AUTHORIZED" if authorized else
                  "COLD_BEYOND_BENCHMARK" if depth > config.normal_prospect_target_max else
                  "ADAPTIVE_WARMUP_CONTINUE")
        evidence["segmentTarget"] = target
        return AdaptiveSalesReadinessDecision(authorized, reason, segment, False, strong,
            depth, position, evidence, {} if authorized else {"commercialProgressionSuppressed": True})

    def persist(self, decision, **values):
        return self.repository.persist_decision(decision, **values)

"""Deterministic WHETHER/WHY policy for autonomous Free Engagement Teasers."""
from datetime import datetime, timezone

from app.models.engagement_teaser_policy import (
    ENGAGEMENT_POLICY_VERSION, EngagementStrategy,
    EngagementTeaserDecision, EngagementTeaserPolicyConfig,
)
from app.repositories.engagement_teaser_policy_repository import EngagementTeaserPolicyRepository
from app.services.customer_value_attention_service import CustomerValueAttentionService


class EngagementTeaserPolicyService:
    """Precedence is RE_ENGAGE, WARM_UP, then RELATIONSHIP."""
    def __init__(self, repository=None, clock=None, customer_value_attention_service=None):
        self.repository = repository or EngagementTeaserPolicyRepository()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.customer_value_attention_service = (
            customer_value_attention_service or CustomerValueAttentionService()
        )

    def evaluate(self, *, creator_profile_id, fanvue_account_id, fanvue_user_id,
                 conversation_thread_id, correlation_id, trigger_type="ACTIVE_INBOUND",
                 authoritative_suppression=None):
        policy = self.repository.active_policy(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)
        if not policy:
            return self._save(EngagementTeaserDecision("SEND_NONE", "ENGAGEMENT_RULE_NOT_ENABLED"),
                correlation_id, creator_profile_id, fanvue_account_id, fanvue_user_id,
                conversation_thread_id, trigger_type)
        config = EngagementTeaserPolicyConfig.from_mapping(policy.get("policy_configuration"))
        version = f"{ENGAGEMENT_POLICY_VERSION}:instruction-v{policy['version']}"
        if authoritative_suppression:
            decision = EngagementTeaserDecision("SEND_NONE", str(authoritative_suppression),
                suppression_evidence={"authority": str(authoritative_suppression)}, policy_version=version)
            return self._save(decision, correlation_id, creator_profile_id, fanvue_account_id,
                              fanvue_user_id, conversation_thread_id, trigger_type)
        evidence = dict(self.repository.snapshot(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, fanvue_user_id=fanvue_user_id,
            conversation_thread_id=conversation_thread_id))
        now = self.clock()
        last_inbound = evidence.get("last_inbound_at")
        last_teaser = evidence.get("last_teaser_at")
        inbound = int(evidence.get("inbound_count") or 0)
        purchase_count = int(evidence.get("purchase_count") or 0)
        age_days = (now-last_inbound).total_seconds()/86400 if last_inbound else None
        teaser_age_days = (now-last_teaser).total_seconds()/86400 if last_teaser else None
        structured = {
            "inboundMessageCount": inbound, "purchaseCount": purchase_count,
            "profileState": evidence.get("profile_state"),
            "daysSinceLastInbound": round(age_days, 2) if age_days is not None else None,
            "daysSinceLastTeaser": round(teaser_age_days, 2) if teaser_age_days is not None else None,
            "inboundMessagesSinceTeaser": int(evidence.get("inbound_since_teaser") or 0),
            "sentInConversation": int(evidence.get("sent_in_conversation") or 0),
            "sentRollingPeriod": sum(1 for sent in (evidence.get("teaser_sent_times") or [])
                if (now-sent).total_seconds()/86400 <= config.rolling_period_days),
        }
        value_attention = self.customer_value_attention_service.project(
            commerce_memory={
                "purchaseCount": purchase_count,
                "lifetimeGrossMinor": int(evidence.get("lifetime_gross_minor") or 0),
                "lastPurchaseAt": evidence.get("last_purchase_at"),
            },
            behavior={
                "inbound_message_count": inbound,
                "commercial_movement": purchase_count > 0,
                "current_inbound_activity": trigger_type == "ACTIVE_INBOUND",
            },
            now=now,
        )
        structured["customerValueAttention"] = dict(value_attention.to_mapping())
        fatigue = self._fatigue(config, structured)
        if fatigue:
            return self._save(EngagementTeaserDecision("SEND_NONE", fatigue,
                evidence=structured, policy_version=version), correlation_id,
                creator_profile_id, fanvue_account_id, fanvue_user_id,
                conversation_thread_id, trigger_type)

        strategy = None; reason = "NO_ENGAGEMENT_STRATEGY_QUALIFIED"
        if value_attention.time_waster_risk == "HIGH" and purchase_count == 0:
            return self._save(EngagementTeaserDecision(
                "SEND_NONE", "CUSTOMER_VALUE_ATTENTION_TAPER_SUPPRESSES_FREE_TEASER",
                evidence=structured, policy_version=version,
            ), correlation_id, creator_profile_id, fanvue_account_id,
                fanvue_user_id, conversation_thread_id, trigger_type)
        if trigger_type == "SCHEDULED_REENGAGEMENT":
            if inbound >= config.meaningful_history_minimum_inbound_messages and age_days is not None \
                    and age_days >= config.dormant_inactivity_days:
                strategy, reason = EngagementStrategy.RE_ENGAGE, "MEANINGFUL_HISTORY_GENUINELY_DORMANT"
        elif age_days is not None and age_days <= config.active_conversation_hours / 24:
            if purchase_count == 0 and config.warm_up_minimum_inbound_messages <= inbound <= 20:
                strategy, reason = EngagementStrategy.WARM_UP, "NEWER_CUSTOMER_HEALTHY_CONVERSATION"
            elif age_days <= config.relationship_recent_activity_days and inbound >= config.relationship_minimum_inbound_messages and (
                purchase_count > 0 or str(evidence.get("profile_state")) in {"REPEAT_BUYER","VIP","HIGH_VALUE"}
            ):
                strategy, reason = EngagementStrategy.RELATIONSHIP, "ESTABLISHED_RECENTLY_ENGAGED_CUSTOMER"
        if strategy is EngagementStrategy.RE_ENGAGE and teaser_age_days is not None \
                and teaser_age_days < config.reengagement_cooldown_days:
            strategy, reason = None, "REENGAGEMENT_COOLDOWN_ACTIVE"
        if strategy is EngagementStrategy.RELATIONSHIP and teaser_age_days is not None \
                and teaser_age_days < config.relationship_cooldown_days:
            strategy, reason = None, "RELATIONSHIP_COOLDOWN_ACTIVE"
        decision = EngagementTeaserDecision(
            "SEND_FREE_ENGAGEMENT_TEASER" if strategy else "SEND_NONE",
            reason, strategy=strategy, evidence=structured, policy_version=version)
        return self._save(decision, correlation_id, creator_profile_id, fanvue_account_id,
                          fanvue_user_id, conversation_thread_id, trigger_type)

    @staticmethod
    def _fatigue(config, evidence):
        if evidence["sentInConversation"] >= config.maximum_per_active_conversation:
            return "ACTIVE_CONVERSATION_LIMIT_REACHED"
        if evidence["sentRollingPeriod"] >= config.maximum_per_rolling_period:
            return "ROLLING_PERIOD_LIMIT_REACHED"
        if evidence["daysSinceLastTeaser"] is not None and evidence["daysSinceLastTeaser"] < config.minimum_days_between_teasers:
            return "MINIMUM_TIME_BETWEEN_TEASERS"
        if evidence["daysSinceLastTeaser"] is not None and evidence["inboundMessagesSinceTeaser"] < config.minimum_messages_between_teasers:
            return "MINIMUM_MESSAGES_BETWEEN_TEASERS"
        return None

    def _save(self, decision, correlation_id, creator, account, customer, thread, trigger):
        saver = getattr(self.repository, "persist_decision", None)
        if callable(saver):
            decision_id = saver(decision, correlation_id=correlation_id,
                creator_profile_id=creator, fanvue_account_id=account,
                fanvue_user_id=customer, conversation_thread_id=thread,
                trigger_type=trigger)
            return EngagementTeaserDecision(**{**decision.__dict__, "decision_id": decision_id})
        return decision

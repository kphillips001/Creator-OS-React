import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.asset_intelligence import AssetIntelligenceProfile, AssetIntelligenceStatus
from app.models.engagement_teaser_policy import EngagementTeaserPolicyConfig, EngagementStrategy
from app.services.engagement_teaser_policy_service import EngagementTeaserPolicyService
from app.services.free_engagement_teaser_caption_service import (
    FreeEngagementTeaserCaptionError, FreeEngagementTeaserCaptionService,
)


NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


class PolicyRepository:
    def __init__(self, snapshot=None, enabled=True, config=None):
        self.value = snapshot or {}
        self.enabled = enabled
        self.config = config or EngagementTeaserPolicyConfig().to_dict()
        self.decisions = []
    def active_policy(self, **_):
        return {"version": 2, "policy_configuration": self.config} if self.enabled else None
    def snapshot(self, **_): return self.value
    def persist_decision(self, decision, **context):
        self.decisions.append((decision, context)); return "decision-1"


def signals(*, inbound=0, last_inbound=None, purchases=0, profile="PROSPECT",
            last_teaser=None, sent_conversation=0, sent_times=(), since=0):
    return {"inbound_count": inbound, "last_inbound_at": last_inbound,
        "purchase_count": purchases, "profile_state": profile,
        "last_teaser_at": last_teaser, "sent_in_conversation": sent_conversation,
        "teaser_sent_times": list(sent_times), "inbound_since_teaser": since}


def evaluate(repository, trigger="ACTIVE_INBOUND", suppression=None):
    return EngagementTeaserPolicyService(repository=repository, clock=lambda: NOW).evaluate(
        creator_profile_id=1, fanvue_account_id=2, fanvue_user_id=3,
        conversation_thread_id=4, correlation_id="corr", trigger_type=trigger,
        authoritative_suppression=suppression)


def test_rule_must_be_explicitly_enabled_and_brand_new_customer_gets_none():
    assert evaluate(PolicyRepository(enabled=False)).reason_code == "ENGAGEMENT_RULE_NOT_ENABLED"
    result = evaluate(PolicyRepository(signals(inbound=1, last_inbound=NOW)))
    assert result.decision == "SEND_NONE" and result.reason_code == "NO_ENGAGEMENT_STRATEGY_QUALIFIED"


def test_warm_up_requires_real_developing_conversation_and_is_not_sales_brain_tease():
    result = evaluate(PolicyRepository(signals(inbound=6, last_inbound=NOW)))
    assert result.decision == "SEND_FREE_ENGAGEMENT_TEASER"
    assert result.strategy is EngagementStrategy.WARM_UP
    assert result.reason_code == "NEWER_CUSTOMER_HEALTHY_CONVERSATION"


@pytest.mark.parametrize("reason", ["ACTIVE_PURCHASE_INTENT", "ACTIVE_SALES_SESSION",
    "PAYMENT_RECONCILIATION_PENDING", "BACK_OFF", "BLOCKED_UNDERAGE"])
def test_authoritative_funnel_or_safety_state_always_suppresses(reason):
    result = evaluate(PolicyRepository(signals(inbound=9, last_inbound=NOW)), suppression=reason)
    assert result.decision == "SEND_NONE" and result.reason_code == reason


def test_reengage_requires_both_meaningful_history_and_dormancy():
    old = NOW - timedelta(days=30)
    shallow = evaluate(PolicyRepository(signals(inbound=1, last_inbound=old)), "SCHEDULED_REENGAGEMENT")
    genuine = evaluate(PolicyRepository(signals(inbound=10, last_inbound=old)), "SCHEDULED_REENGAGEMENT")
    assert shallow.decision == "SEND_NONE"
    assert genuine.strategy is EngagementStrategy.RE_ENGAGE


def test_relationship_uses_engagement_plus_customer_history_not_spend_alone():
    active = evaluate(PolicyRepository(signals(inbound=14, last_inbound=NOW, purchases=1)))
    high_spend_no_engagement = evaluate(PolicyRepository(signals(inbound=1, last_inbound=NOW,
        purchases=20, profile="HIGH_VALUE")))
    assert active.strategy is EngagementStrategy.RELATIONSHIP
    assert high_spend_no_engagement.decision == "SEND_NONE"


def test_frequency_and_fatigue_are_deterministic_and_configured():
    recent = NOW - timedelta(days=2)
    result = evaluate(PolicyRepository(signals(inbound=14, last_inbound=NOW,
        purchases=1, last_teaser=recent, sent_times=(recent,), since=20)))
    assert result.reason_code == "MINIMUM_TIME_BETWEEN_TEASERS"
    result = evaluate(PolicyRepository(signals(inbound=14, last_inbound=NOW,
        purchases=1, sent_conversation=1)))
    assert result.reason_code == "ACTIVE_CONVERSATION_LIMIT_REACHED"


class Training:
    def runtime_prompt_block(self, **_): return "Never use the word baby. Solo content only."
class Intelligence:
    def get_profile(self, _):
        return AssetIntelligenceProfile(asset_id=400, creator_profile_id=1,
            analysis_status=AssetIntelligenceStatus.READY, setting="studio",
            pose="seated", mood="playful", clothing=("black dress",), themes=("portrait",))
class GPT:
    def __init__(self, output): self.output = output; self.context = None
    def generate_free_engagement_teaser_caption(self, **context):
        self.context = context; return self.output


def test_caption_is_grounded_in_ready_intelligence_and_global_training():
    gpt = GPT("Thought this might make you smile ✨")
    caption = FreeEngagementTeaserCaptionService(asset_intelligence_repository=Intelligence(),
        ai_training_service=Training(), gpt_service=gpt).generate(asset_id=400,
        strategy="RELATIONSHIP", creator_profile_id=1, fanvue_account_id=2,
        recent_conversation=[{"direction": "outbound", "text": "How was your day?"}])
    assert caption == gpt.output
    assert gpt.context["grounded_asset_context"]["setting"] == "studio"
    assert "baby" in gpt.context["global_conversation_training"]


@pytest.mark.parametrize("caption", ["", "unlock this for $10", "https://example.test"])
def test_unsafe_or_failed_caption_means_send_none(caption):
    service = FreeEngagementTeaserCaptionService(asset_intelligence_repository=Intelligence(),
        ai_training_service=Training(), gpt_service=GPT(caption))
    with pytest.raises(FreeEngagementTeaserCaptionError):
        service.generate(asset_id=400, strategy="WARM_UP", creator_profile_id=1,
                         fanvue_account_id=2)

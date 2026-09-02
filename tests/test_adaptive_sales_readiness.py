from pathlib import Path

import pytest

from app.models.adaptive_sales_readiness import AdaptiveSalesReadinessConfig
from app.services.adaptive_sales_readiness_service import AdaptiveSalesReadinessService
from app.services.ai_training_control_service import AiTrainingControlService
from app.services.conversational_sales_progression_service import ConversationalSalesProgressionService


class Repository:
    def __init__(self, depth, *, lifetime=None, teaser=None, enabled=True):
        self.depth = depth
        self.lifetime = depth if lifetime is None else lifetime
        self.teaser = teaser or {}
        self.enabled = enabled
        self.persisted = []

    def active_policy(self, **_):
        return {"policy_configuration": AdaptiveSalesReadinessConfig().to_dict()} if self.enabled else None

    def snapshot(self, **_):
        return {"warmup_depth": self.depth, "lifetime_inbound_depth": self.lifetime,
                "window_started_at": None, "teaser_response": self.teaser}

    def persist_decision(self, decision, **values):
        self.persisted.append((decision, values))
        return "decision-id"


def evaluate(depth, message="just chatting", *, requests=("one", "two"), purchase_count=0,
             lifetime=None, teaser=None, session=False):
    service = AdaptiveSalesReadinessService(
        repository=Repository(depth, lifetime=lifetime, teaser=teaser),
        direct_intent_detector=ConversationalSalesProgressionService().has_direct_purchase_intent)
    return service.evaluate(creator_profile_id=1, fanvue_account_id=2, fanvue_user_id=3,
        conversation_thread_id=4, buyer_stage="PROSPECT", purchase_count=purchase_count,
        context={"latest_message": message, "recent_conversation_requests": requests,
                 **({"sales_session_id": "session"} if session else {})})


@pytest.mark.parametrize("depth", [1, 3, 9])
def test_normal_new_prospect_keeps_warming_early(depth):
    result = evaluate(depth)
    assert result.authorized is False
    assert result.reason_code == "ADAPTIVE_WARMUP_CONTINUE"


def test_benchmark_is_advisory_and_cold_customer_waits_beyond_fifteen():
    result = evaluate(20, message="ok", requests=())
    assert result.authorized is False
    assert result.reason_code == "COLD_BEYOND_BENCHMARK"


def test_healthy_depth_can_authorize_tease_but_flirtation_alone_cannot():
    assert evaluate(12, message="I love talking with you").authorized is True
    assert evaluate(12, message="you're so hot", requests=()).authorized is False


def test_direct_purchase_intent_bypasses_only_warmup():
    result = evaluate(1, message="How much is the set?")
    assert result.authorized is True
    assert result.direct_intent is True
    assert result.reason_code == "DIRECT_PURCHASE_INTENT_BYPASS"
    assert evaluate(20, message="How much?", session=True).authorized is False


@pytest.mark.parametrize("message", [
    "What can I buy?", "What do you have?", "Do you have anything I can unlock?",
    "Where can I get more?", "I want that.", "Send me something.",
])
def test_supported_direct_intent_examples_accelerate(message):
    assert evaluate(1, message=message).reason_code == "DIRECT_PURCHASE_INTENT_BYPASS"


def test_buyers_accelerate_but_are_not_automatically_sold_to():
    assert evaluate(6, purchase_count=1).authorized is True
    assert evaluate(6, purchase_count=1, requests=()).authorized is False
    assert evaluate(4, purchase_count=2).authorized is True


def test_teaser_send_is_not_evidence_but_actual_response_is_modest_evidence():
    sent_only = {"strategy": "WARM_UP", "next_inbound_at": None}
    responded = {"strategy": "WARM_UP", "next_inbound_at": "2026-08-24T00:00:00Z",
                 "response_attribution": "NEXT_INBOUND"}
    assert evaluate(10, teaser=sent_only, requests=()).authorized is False
    assert evaluate(10, teaser=responded).evidence["adjustments"]["freeTeaserResponse"] is True


def test_old_record_without_meaningful_history_is_not_returning_relationship():
    assert evaluate(2, lifetime=2).segment == "PROSPECT"
    assert evaluate(2, lifetime=15).segment == "RETURNING_NON_BUYER"


def test_ai_training_recognizes_only_supported_structured_sales_policy():
    preview = AiTrainingControlService(repository=object()).classify(
        "Build rapport before proactively selling and present paid content when the customer appears ready. "
        "Around 10-15 customer messages is a warm-up benchmark. Use responses to free teasers.")
    assert preview["instructionType"] == "SALES_RULE"
    assert preview["policyKey"] == "ADAPTIVE_SALES_READINESS"
    assert preview["enforcementMode"] == "BACKEND"
    assert preview["runtimeEligible"] is True
    assert preview["policyConfiguration"]["benchmark_never_forces_offer"] is True


def test_migration_declares_durable_projection_and_policy_shape():
    sql = Path("migrations/forward/20260824_088_adaptive_sales_readiness.sql").read_text(encoding="utf-8")
    assert "sales_readiness_decisions" in sql
    assert "ADAPTIVE_SALES_READINESS" in sql
    assert "warmup_depth" in sql and "resulting_sales_action" in sql

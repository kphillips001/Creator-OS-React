import logging

import pytest

from app.services.decision_engine_intimacy_integration_service import (
    DecisionEngineIntimacyIntegrationService,
)
from app.services.gpt_service import GPTService


AUTHORITY = "COMMERCE_BACKED_AUTHORITATIVE_VALUE"


def canonical(*, tier, purchases, stage="REPEAT_BUYER", relationship="ELEVATED"):
    return {
        "customer_value_authority": AUTHORITY,
        "buyer_tier": tier,
        "buyer_stage": stage,
        "purchase_count": purchases,
        "relationship_investment": relationship,
        "last_purchase_at": "2026-08-31T12:00:00+00:00",
    }


@pytest.mark.parametrize(
    ("buyer", "expected"),
    [
        (canonical(tier="PROSPECT", purchases=0, stage="PROSPECT"), "GATED"),
        (canonical(tier="BUYER", purchases=1, stage="FIRST_TIME_BUYER"), "LIMITED"),
        (canonical(tier="REPEAT_BUYER", purchases=2), "ELEVATED"),
        (canonical(tier="HIGH_VALUE", purchases=3), "PREMIUM"),
        (canonical(tier="WHALE", purchases=8, relationship="HIGHEST"), "VIP"),
    ],
)
def test_canonical_buyer_value_derives_graduated_entitlement(buyer, expected):
    result = DecisionEngineIntimacyIntegrationService().build_overrides(
        {
            "buyer_tier": "WHALE",  # conflicting legacy value must lose
            "premium_sexting_allowed": True,
            "explicit_allowed": True,
        },
        canonical_buyer_memory=buyer,
    )
    assert result["intimacy_entitlement"] == expected
    assert result["canonical_buyer_authority_used"] is True
    assert result["legacy_buyer_memory_authority_used"] is False
    assert result["buyer_tier"] == buyer["buyer_tier"]


def test_only_premium_or_vip_entitlement_enables_adult_generation():
    service = DecisionEngineIntimacyIntegrationService()
    entry = service.build_overrides(
        {"premium_sexting_allowed": True, "explicit_allowed": True},
        canonical_buyer_memory=canonical(
            tier="BUYER", purchases=1, stage="FIRST_TIME_BUYER"
        ),
    )
    premium = service.build_overrides(
        {"premium_sexting_allowed": True, "explicit_allowed": True},
        canonical_buyer_memory=canonical(tier="HIGH_VALUE", purchases=4),
    )
    assert entry["adult_generation_allowed"] is False
    assert premium["adult_generation_allowed"] is True


def test_hot_active_repeat_buyer_gets_bounded_current_momentum_elevation():
    result = DecisionEngineIntimacyIntegrationService().build_overrides(
        {"premium_sexting_allowed": True, "explicit_allowed": True},
        runtime_state={
            "active_buying_window": True,
            "current_commercial_momentum": "HOT",
        },
        canonical_buyer_memory=canonical(tier="REPEAT_BUYER", purchases=2),
    )
    assert result["intimacy_entitlement"] == "PREMIUM"
    assert result["intimacy_investment_inputs"][
        "momentumElevatedCurrentInvestment"
    ] is True
    assert result["buyer_tier"] == "REPEAT_BUYER"


def test_non_explicit_topic_has_no_intimacy_prompt_even_for_whale():
    assert GPTService._build_intimacy_entitlement_instruction({
        "intimacy_entitlement": "VIP",
        "explicit_requested": False,
        "gpt_classifier_result": {"sexual_engagement": False},
    }) == ""


def test_nonbuyer_explicit_prompt_establishes_bounded_premium_boundary():
    instruction = GPTService._build_intimacy_entitlement_instruction({
        "intimacy_entitlement": "GATED",
        "explicit_requested": True,
    })
    assert "do not provide sustained premium explicit interaction" in instruction
    assert "never creates" in instruction
    assert "Sales Brain remains the only commercial authority" in instruction


def test_grok_failure_uses_one_openai_fallback_in_same_generation_call():
    calls = []
    preview = {}

    def grok():
        calls.append("GROK")
        raise TimeoutError("provider unavailable")

    def openai():
        calls.append("OPENAI")
        return "bounded fallback"

    result = GPTService._execute_provider_completion(
        selected_provider="GROK",
        primary_complete=grok,
        fallback_complete=openai,
        provider_preview=preview,
        logger=logging.getLogger(__name__),
    )
    assert result == "bounded fallback"
    assert calls == ["GROK", "OPENAI"]
    assert preview == {
        "responseProvider": "OPENAI",
        "grokAttempted": True,
        "grokSucceeded": False,
        "providerFallbackAttempted": True,
        "providerFallbackProvider": "OPENAI",
        "providerFallbackOutcome": "SUCCEEDED",
    }


def test_openai_failure_does_not_loop_or_invoke_fallback():
    fallback_calls = []
    with pytest.raises(RuntimeError, match="failed"):
        GPTService._execute_provider_completion(
            selected_provider="OPENAI",
            primary_complete=lambda: (_ for _ in ()).throw(RuntimeError("failed")),
            fallback_complete=lambda: fallback_calls.append(True),
            provider_preview={},
            logger=logging.getLogger(__name__),
        )
    assert fallback_calls == []

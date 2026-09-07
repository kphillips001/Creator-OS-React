from datetime import datetime, timedelta, timezone

import logging

from app.services.customer_value_attention_service import CustomerValueAttentionService
from app.services.decision_engine_intimacy_integration_service import (
    DecisionEngineIntimacyIntegrationService,
)
from app.services.gpt_service import GPTService
from app.services.realtime_intimacy_reinforcement_service import (
    RealtimeIntimacyReinforcementService,
)


AUTHORITY = "COMMERCE_BACKED_AUTHORITATIVE_VALUE"
NOW = datetime.now(timezone.utc)


def canonical(*, tier, purchases, last_purchase_at=None):
    return {
        "customer_value_authority": AUTHORITY,
        "buyer_tier": tier,
        "buyer_stage": (
            "PROSPECT" if purchases == 0 else
            "FIRST_TIME_BUYER" if purchases == 1 else
            "HIGH_VALUE_BUYER" if tier in {"HIGH_VALUE", "WHALE"} else
            "REPEAT_BUYER"
        ),
        "purchase_count": purchases,
        "last_purchase_at": (last_purchase_at or NOW).isoformat(),
        "relationship_investment": "ELEVATED",
    }


def overrides(*, tier, purchases, active=False, momentum="INACTIVE",
              last_purchase_at=None, legacy=None):
    return DecisionEngineIntimacyIntegrationService().build_overrides(
        legacy or {},
        runtime_state={
            "active_buying_window": active,
            "current_commercial_momentum": momentum,
        },
        canonical_buyer_memory=canonical(
            tier=tier, purchases=purchases,
            last_purchase_at=last_purchase_at,
        ),
    )


def route(result, explicit=True):
    return DecisionEngineIntimacyIntegrationService.select_provider(
        result, explicit_requested=explicit,
    )


def test_zero_spend_and_legacy_claims_cannot_reach_grok():
    result = overrides(
        tier="PROSPECT", purchases=0,
        legacy={
            "buyer_tier": "WHALE",
            "premium_sexting_allowed": True,
            "explicit_allowed": True,
        },
    )
    assert result["intimacy_entitlement"] == "GATED"
    assert result["premium_sexting_allowed"] is False
    assert result["legacy_premium_sexting_allowed"] is True
    assert route(result)["selected_provider"] == "OPENAI"


def test_first_buyer_is_limited_and_repeat_buyer_is_elevated():
    first = overrides(tier="BUYER", purchases=1)
    repeat = overrides(tier="REPEAT_BUYER", purchases=2)
    assert first["intimacy_entitlement"] == "LIMITED"
    assert repeat["intimacy_entitlement"] == "ELEVATED"
    assert route(first)["grok_eligible"] is False
    assert route(repeat)["grok_eligible"] is False


def test_hot_active_repeat_buyer_has_temporary_premium_without_value_rewrite():
    hot = overrides(
        tier="REPEAT_BUYER", purchases=2, active=True, momentum="HOT",
    )
    cooled = overrides(
        tier="REPEAT_BUYER", purchases=2, active=False, momentum="COLD",
    )
    assert hot["base_intimacy_entitlement"] == "ELEVATED"
    assert hot["intimacy_entitlement"] == "PREMIUM"
    assert hot["buyer_tier"] == "REPEAT_BUYER"
    assert route(hot)["preferred_provider"] == "GROK"
    assert cooled["intimacy_entitlement"] == "ELEVATED"
    assert route(cooled)["preferred_provider"] == "OPENAI"


def test_high_value_and_whale_controlled_routing_checkpoints():
    high = overrides(tier="HIGH_VALUE", purchases=1)
    whale = overrides(tier="WHALE", purchases=1)
    assert (high["intimacy_entitlement"], route(high)["preferred_provider"]) == (
        "PREMIUM", "GROK",
    )
    assert (whale["intimacy_entitlement"], route(whale)["preferred_provider"]) == (
        "VIP", "GROK",
    )
    assert route(high, explicit=False)["preferred_provider"] == "OPENAI"
    assert route(whale, explicit=False)["preferred_provider"] == "OPENAI"


def test_large_single_verified_purchase_uses_canonical_value_thresholds():
    service = CustomerValueAttentionService()
    high = service.project(commerce_memory={
        "schemaVersion": "customer_commerce_memory_v1",
        "verifiedPurchaseCount": 1,
        "lifetimeGrossMinor": 15_000,
    })
    whale = service.project(commerce_memory={
        "schemaVersion": "customer_commerce_memory_v1",
        "verifiedPurchaseCount": 1,
        "lifetimeGrossMinor": 50_000,
    })
    assert (high.value_tier, high.buyer_stage) == ("HIGH_VALUE", "HIGH_VALUE_BUYER")
    assert (whale.value_tier, whale.buyer_stage) == ("WHALE", "HIGH_VALUE_BUYER")


def test_cooling_and_dormant_value_retain_entitlement_but_taper_investment():
    cooling_high = overrides(
        tier="HIGH_VALUE", purchases=3,
        last_purchase_at=NOW - timedelta(days=30),
    )
    dormant_whale = overrides(
        tier="WHALE", purchases=5,
        last_purchase_at=NOW - timedelta(days=90),
    )
    fresh_whale = overrides(tier="WHALE", purchases=6)
    assert cooling_high["intimacy_entitlement"] == "PREMIUM"
    assert cooling_high["intimacy_investment"] == "SUSTAINED_BUT_BOUNDED_INTIMACY"
    assert dormant_whale["intimacy_entitlement"] == "VIP"
    assert dormant_whale["intimacy_investment"] == "BOUNDED_INTIMACY_REWARM"
    assert route(dormant_whale)["grok_eligible"] is True
    assert fresh_whale["intimacy_investment"] == "HIGHEST_APPROPRIATE_INTIMACY"


def test_purchase_created_does_not_reinforce_but_confirmed_purchase_does():
    service = RealtimeIntimacyReinforcementService()
    created = service.build_updates_from_event("purchase_created", {})
    confirmed = service.build_updates_from_event("purchase_received", {})
    assert "premium_sexting_allowed" not in created
    assert created["runtime_mode"] == "safe_chat"
    assert confirmed["premium_sexting_allowed"] is True
    assert confirmed["explicit_allowed"] is True


def test_grok_fallback_is_normal_openai_ava_with_truthful_diagnostics():
    calls = []
    preview = {}
    result = GPTService._execute_provider_completion(
        selected_provider="GROK",
        primary_complete=lambda: (_ for _ in ()).throw(TimeoutError("unavailable")),
        fallback_complete=lambda: calls.append("OPENAI") or "normal Ava",
        provider_preview=preview,
        logger=logging.getLogger(__name__),
    )
    fallback_messages = GPTService._openai_grok_fallback_messages([
        {"role": "user", "content": "qualifying premium-intimacy request"},
    ])
    assert result == "normal Ava"
    assert calls == ["OPENAI"]
    assert preview["preferredProvider"] == "GROK"
    assert preview["responseProvider"] == "OPENAI"
    assert preview["fallbackReason"] == "GROK_UNAVAILABLE"
    assert "normal Ava" in fallback_messages[-1]["content"]
    assert "do not attempt to reproduce" in fallback_messages[-1]["content"]

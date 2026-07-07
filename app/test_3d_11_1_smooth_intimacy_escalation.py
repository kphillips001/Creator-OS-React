from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)


def run_test():
    print("\n==============================")
    print(" 3D.11.1 SMOOTH INTIMACY TEST")
    print("==============================\n")

    service = SmoothIntimacyEscalationService()

    print("Test 1: free user stays low intensity...")
    result = service.build_escalation_profile(
        intimacy_context={
            "intimacy_tier": "safe",
            "runtime_mode": "safe_chat",
        },
        spend_profile={
            "buyer_tier": "NON_BUYER",
            "total_spend": 0,
            "purchase_count": 0,
        },
        conversation_state={
            "conversation_mode": "casual",
            "heat_score": 20,
            "intent_score": 10,
        },
    )

    assert result["success"] is True
    assert result["escalation_stage"] == "soft_flirt"
    assert result["explicit_jump_blocked"] is True
    print("✅ Passed\n")

    print("Test 2: first purchase does NOT jump too fast...")
    result = service.build_escalation_profile(
        intimacy_context={
            "intimacy_tier": "premium",
            "runtime_mode": "premium_gate",
            "spender_confidence": "high",
        },
        spend_profile={
            "buyer_tier": "LOW_SPENDER",
            "total_spend": 20,
            "purchase_count": 1,
            "recent_purchase_active": True,
        },
        conversation_state={
            "conversation_mode": "flirty",
            "heat_score": 65,
            "intent_score": 60,
        },
    )

    assert result["success"] is True
    assert result["explicit_jump_blocked"] is True
    assert result["pacing_directive"] == "post_purchase_slow_build"
    print("✅ Passed\n")

    print("Test 3: repeat active buyer can escalate gradually...")
    result = service.build_escalation_profile(
        intimacy_context={
            "intimacy_tier": "premium",
            "runtime_mode": "premium_gate",
            "spender_confidence": "high",
        },
        spend_profile={
            "buyer_tier": "ACTIVE_BUYER",
            "total_spend": 125,
            "purchase_count": 4,
            "recent_purchase_active": True,
        },
        conversation_state={
            "conversation_mode": "tension",
            "heat_score": 85,
            "intent_score": 80,
        },
    )

    assert result["success"] is True
    assert result["explicit_jump_blocked"] is False
    assert result["max_intimacy_intensity"] in [
        "medium",
        "medium_high",
        "high",
    ]
    print("✅ Passed\n")

    print("Test 4: whale gets premium but controlled pacing...")
    result = service.build_escalation_profile(
        intimacy_context={
            "intimacy_tier": "premium",
            "runtime_mode": "premium_gate",
            "spender_confidence": "high",
        },
        spend_profile={
            "buyer_tier": "WHALE",
            "total_spend": 1500,
            "purchase_count": 25,
        },
        conversation_state={
            "conversation_mode": "conversion",
            "heat_score": 90,
            "intent_score": 90,
        },
    )

    assert result["success"] is True
    assert result["escalation_stage"] == "exclusive_premium"
    assert result["pacing_directive"] == "slow_premium"
    print("✅ Passed\n")

    print("==============================")
    print("✅ 3D.11.1 PASSED")
    print("==============================\n")


if __name__ == "__main__":
    run_test()
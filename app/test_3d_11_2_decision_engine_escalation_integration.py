from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)


def run_test():
    print("\n====================================")
    print(" 3D.11.2 DECISION ENGINE INTEGRATION")
    print("====================================\n")

    service = SmoothIntimacyEscalationService()

    user_memory = {
        "buyer_tier": "LOW_SPENDER",
        "total_spend": 25,
        "purchase_count": 1,
        "recent_purchase_active": True,
        "runtime_mode": "premium_gate",
        "spender_confidence": "high",
        "heat_score": 65,
        "intent_score": 60,
        "conversation_mode": "flirty",
    }

    intimacy_overrides = {
        "intimacy_tier": "premium",
        "runtime_mode": "premium_gate",
        "spender_confidence": "high",
    }

    profile = service.build_escalation_profile(
        intimacy_context=intimacy_overrides,
        spend_profile=user_memory,
        buyer_memory=user_memory,
        conversation_state={
            "conversation_mode": "flirty",
            "heat_score": 65,
            "intent_score": 60,
            "buyer_session_state": None,
        },
    )

    print(profile)

    assert profile["success"] is True
    assert profile["should_smooth_escalation"] is True
    assert profile["explicit_jump_blocked"] is True
    assert profile["pacing_directive"] == "post_purchase_slow_build"
    assert "gpt_instruction" in profile

    print("\n✅ 3D.11.2 PASSED\n")


if __name__ == "__main__":
    run_test()
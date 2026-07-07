from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)


def validate_result(result):
    assert result["success"] is True

    assert result["max_intimacy_intensity"] in [
        "low",
        "medium_low",
        "medium",
        "medium_high",
        "high",
    ]

    assert result["pacing_directive"] != ""

    assert isinstance(
        result["reasons"],
        list,
    )

    assert (
        result["gpt_instruction"]
        != ""
    )


def run_test():
    print("\n====================================")
    print(" 3D.11.11 PRODUCTION VALIDATION")
    print("====================================\n")

    service = SmoothIntimacyEscalationService()

    # --------------------------------------------------
    # SCENARIO 1
    # ACTIVE PREMIUM BUYER
    # --------------------------------------------------

    active_buyer = (
        service.build_escalation_profile(
            intimacy_context={
                "intimacy_tier": "premium",
                "runtime_mode": "premium_gate",
                "spender_confidence": "high",
            },
            spend_profile={
                "purchase_count": 10,
                "tip_count": 6,
                "total_spend": 1200,
            },
            conversation_state={
                "conversation_mode": "conversion",
                "heat_score": 90,
                "intent_score": 90,
                "buyer_momentum_score": 70,
                "relationship_depth_score": 70,
                "engagement_depth_score": 70,
                "conversation_streak": 14,
                "recent_escalation_active": True,
            },
        )
    )

    print("\n--- ACTIVE PREMIUM BUYER ---")
    print(active_buyer)

    validate_result(active_buyer)

    # --------------------------------------------------
    # SCENARIO 2
    # EARLY BUYER SESSION
    # --------------------------------------------------

    early_session = (
        service.build_escalation_profile(
            intimacy_context={
                "intimacy_tier": "premium",
                "runtime_mode": "premium_gate",
                "spender_confidence": "medium",
            },
            spend_profile={
                "purchase_count": 1,
                "tip_count": 0,
                "total_spend": 35,
            },
            conversation_state={
                "conversation_mode": "flirty",
                "buyer_session_active": True,
                "buyer_session_step": 1,
                "buyer_momentum_score": 15,
                "relationship_depth_score": 15,
                "engagement_depth_score": 10,
            },
        )
    )

    print("\n--- EARLY BUYER SESSION ---")
    print(early_session)

    validate_result(early_session)

    assert (
        early_session[
            "explicit_jump_blocked"
        ]
        is True
    )

    # --------------------------------------------------
    # SCENARIO 3
    # COOLDOWN DECAY STATE
    # --------------------------------------------------

    cooldown_state = (
        service.build_escalation_profile(
            intimacy_context={
                "intimacy_tier": "premium",
                "runtime_mode": "premium_gate",
                "spender_confidence": "high",
            },
            spend_profile={
                "purchase_count": 8,
                "tip_count": 5,
                "total_spend": 500,
            },
            conversation_state={
                "conversation_mode": "tension",
                "intimacy_cooldown_active": True,
                "cooldown_decay_level": 80,
                "recent_escalation_active": True,
            },
        )
    )

    print("\n--- COOLDOWN STATE ---")
    print(cooldown_state)

    validate_result(cooldown_state)

    assert (
        cooldown_state[
            "max_intimacy_intensity"
        ]
        == "low"
    )

    # --------------------------------------------------
    # SCENARIO 4
    # SAFE MODE FREE USER
    # --------------------------------------------------

    safe_mode = (
        service.build_escalation_profile(
            intimacy_context={
                "intimacy_tier": "free",
                "runtime_mode": "safe_chat",
                "spender_confidence": "low",
            },
            spend_profile={
                "purchase_count": 0,
                "tip_count": 0,
                "total_spend": 0,
            },
            conversation_state={
                "conversation_mode": "casual",
                "heat_score": 20,
                "intent_score": 15,
            },
        )
    )

    print("\n--- SAFE MODE USER ---")
    print(safe_mode)

    validate_result(safe_mode)

    assert (
        safe_mode[
            "explicit_jump_blocked"
        ]
        is True
    )

    print("\n✅ 3D.11.11 PASSED\n")


if __name__ == "__main__":
    run_test()
from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)


def print_case(title, result):
    print(f"\n--- {title} ---")
    print(result)


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


def run_test():
    print("\n====================================")
    print(" 3D.11.10 STRESS VALIDATION")
    print("====================================\n")

    service = SmoothIntimacyEscalationService()

    # --------------------------------------------------
    # FREE USER + HIGH HEAT
    # --------------------------------------------------

    free_high_heat = (
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
                "conversation_mode": "conversion",
                "heat_score": 95,
                "intent_score": 95,
            },
        )
    )

    print_case(
        "FREE USER + HIGH HEAT",
        free_high_heat,
    )

    validate_result(free_high_heat)

    assert (
        free_high_heat["explicit_jump_blocked"]
        is True
    )

    # --------------------------------------------------
    # WHALE + CASUAL MODE
    # --------------------------------------------------

    whale_casual = (
        service.build_escalation_profile(
            intimacy_context={
                "intimacy_tier": "premium",
                "runtime_mode": "premium_gate",
                "spender_confidence": "high",
            },
            spend_profile={
                "purchase_count": 50,
                "tip_count": 30,
                "total_spend": 5000,
            },
            conversation_state={
                "conversation_mode": "casual",
                "buyer_momentum_score": 100,
                "relationship_depth_score": 100,
                "engagement_depth_score": 100,
            },
        )
    )

    print_case(
        "WHALE + CASUAL MODE",
        whale_casual,
    )

    validate_result(whale_casual)

    assert (
        whale_casual["max_intimacy_intensity"]
        in ["medium_low", "medium"]
    )

    # --------------------------------------------------
    # PREMIUM + LOW CONFIDENCE
    # --------------------------------------------------

    premium_low_confidence = (
        service.build_escalation_profile(
            intimacy_context={
                "intimacy_tier": "premium",
                "runtime_mode": "premium_gate",
                "spender_confidence": "low",
            },
            spend_profile={
                "purchase_count": 15,
                "tip_count": 5,
                "total_spend": 800,
            },
            conversation_state={
                "conversation_mode": "tension",
                "buyer_momentum_score": 80,
                "relationship_depth_score": 80,
                "engagement_depth_score": 80,
            },
        )
    )

    print_case(
        "PREMIUM + LOW CONFIDENCE",
        premium_low_confidence,
    )

    validate_result(
        premium_low_confidence
    )

    assert (
        premium_low_confidence[
            "premium_guard_triggered"
        ]
        is True
    )

    # --------------------------------------------------
    # COOLDOWN + CLOSE MODE
    # --------------------------------------------------

    cooldown_close = (
        service.build_escalation_profile(
            intimacy_context={
                "intimacy_tier": "premium",
                "runtime_mode": "premium_gate",
                "spender_confidence": "high",
            },
            spend_profile={
                "purchase_count": 8,
                "tip_count": 3,
                "total_spend": 400,
            },
            conversation_state={
                "conversation_mode": "close",
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_action": "close_mode",
                "intimacy_cooldown_active": True,
                "cooldown_decay_level": 85,
            },
        )
    )

    print_case(
        "COOLDOWN + CLOSE MODE",
        cooldown_close,
    )

    validate_result(cooldown_close)

    assert (
        cooldown_close[
            "max_intimacy_intensity"
        ]
        == "low"
    )

    # --------------------------------------------------
    # REALTIME PURCHASE + COOLDOWN OVERLAP
    # --------------------------------------------------

    realtime_overlap = (
        service.build_escalation_profile(
            intimacy_context={
                "intimacy_tier": "premium",
                "runtime_mode": "premium_gate",
                "spender_confidence": "high",
            },
            spend_profile={
                "purchase_count": 2,
                "tip_count": 1,
                "total_spend": 120,
            },
            conversation_state={
                "conversation_mode": "conversion",
                "recent_escalation_active": True,
                "post_purchase_cooldown": True,
                "cooldown_decay_level": 50,
            },
        )
    )

    print_case(
        "REALTIME PURCHASE OVERLAP",
        realtime_overlap,
    )

    validate_result(realtime_overlap)

    print("\n✅ 3D.11.10 PASSED\n")


if __name__ == "__main__":
    run_test()
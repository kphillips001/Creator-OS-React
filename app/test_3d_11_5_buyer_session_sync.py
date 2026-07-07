from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.11.5 BUYER SESSION SYNC")
    print("====================================\n")

    service = SmoothIntimacyEscalationService()

    base_intimacy = {
        "intimacy_tier": "premium",
        "runtime_mode": "premium_gate",
        "spender_confidence": "high",
    }

    base_spend = {
        "buyer_tier": "ACTIVE_BUYER",
        "purchase_count": 4,
        "total_spend": 150,
    }

    # --------------------------------------------------
    # STEP 1
    # --------------------------------------------------

    step1 = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "tension",
            "buyer_session_active": True,
            "buyer_session_step": 1,
        },
    )

    print_result("STEP 1", step1)

    assert step1["explicit_jump_blocked"] is True

    # --------------------------------------------------
    # STEP 2
    # --------------------------------------------------

    step2 = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "tension",
            "buyer_session_active": True,
            "buyer_session_step": 2,
        },
    )

    print_result("STEP 2", step2)

    assert (
        step2["pacing_directive"]
        == "controlled_ppv_build"
    )

    # --------------------------------------------------
    # CLOSE MODE
    # --------------------------------------------------

    close_mode = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "conversion",
            "buyer_session_active": True,
            "buyer_session_step": 3,
            "buyer_session_action": "close_mode",
        },
    )

    print_result("CLOSE MODE", close_mode)

    assert (
        close_mode["pacing_directive"]
        == "close_mode"
    )

    assert (
        close_mode["explicit_jump_blocked"]
        is False
    )

    # --------------------------------------------------
    # EXIT SESSION
    # --------------------------------------------------

    exit_mode = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "casual",
            "buyer_session_active": True,
            "buyer_session_step": 0,
            "buyer_session_action": "exit_session",
        },
    )

    print_result("EXIT SESSION", exit_mode)

    assert exit_mode["max_intimacy_intensity"] == "low"

    print("\n✅ 3D.11.5 PASSED\n")


if __name__ == "__main__":
    run_test()
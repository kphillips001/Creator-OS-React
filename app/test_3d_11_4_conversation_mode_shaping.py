from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.11.4 CONVERSATION MODE SHAPING")
    print("====================================\n")

    service = SmoothIntimacyEscalationService()

    base_intimacy = {
        "intimacy_tier": "premium",
        "runtime_mode": "premium_gate",
        "spender_confidence": "high",
    }

    base_spend = {
        "buyer_tier": "ACTIVE_BUYER",
        "purchase_count": 3,
        "total_spend": 120,
    }

    # --------------------------------------------------
    # CASUAL MODE
    # --------------------------------------------------

    casual = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "casual",
            "heat_score": 20,
            "intent_score": 15,
        },
    )

    print_result("CASUAL", casual)

    assert casual["explicit_jump_blocked"] is True

    # --------------------------------------------------
    # FLIRTY MODE
    # --------------------------------------------------

    flirty = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "flirty",
            "heat_score": 50,
            "intent_score": 40,
        },
    )

    print_result("FLIRTY", flirty)

    assert flirty["max_intimacy_intensity"] in [
        "medium",
        "medium_high",
    ]

    # --------------------------------------------------
    # TENSION MODE
    # --------------------------------------------------

    tension = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "tension",
            "heat_score": 80,
            "intent_score": 70,
        },
    )

    print_result("TENSION", tension)

    assert tension["pacing_directive"] == "controlled"

    # --------------------------------------------------
    # CONVERSION MODE
    # --------------------------------------------------

    conversion = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "conversion",
            "heat_score": 90,
            "intent_score": 90,
        },
    )

    print_result("CONVERSION", conversion)

    assert conversion["explicit_jump_blocked"] is False

    print("\n✅ 3D.11.4 PASSED\n")


if __name__ == "__main__":
    run_test()
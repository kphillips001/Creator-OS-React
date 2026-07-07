from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.11.7 ESCALATION DECAY")
    print("====================================\n")

    service = SmoothIntimacyEscalationService()

    base_intimacy = {
        "intimacy_tier": "premium",
        "runtime_mode": "premium_gate",
        "spender_confidence": "high",
    }

    base_spend = {
        "purchase_count": 5,
        "tip_count": 5,
        "total_spend": 250,
    }

    # --------------------------------------------------
    # LIGHT DECAY
    # --------------------------------------------------

    light = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "tension",
            "intimacy_cooldown_active": True,
            "cooldown_decay_level": 20,
        },
    )

    print_result("LIGHT", light)

    assert (
        "light_escalation_decay"
        in light["reasons"]
    )

    # --------------------------------------------------
    # MEDIUM DECAY
    # --------------------------------------------------

    medium = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "tension",
            "intimacy_cooldown_active": True,
            "cooldown_decay_level": 50,
        },
    )

    print_result("MEDIUM", medium)

    assert (
        "medium_escalation_decay"
        in medium["reasons"]
    )

    # --------------------------------------------------
    # HEAVY DECAY
    # --------------------------------------------------

    heavy = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "tension",
            "intimacy_cooldown_active": True,
            "cooldown_decay_level": 90,
        },
    )

    print_result("HEAVY", heavy)

    assert heavy["max_intimacy_intensity"] == "low"

    # --------------------------------------------------
    # POST PURCHASE COOLDOWN
    # --------------------------------------------------

    post_purchase = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile=base_spend,
        conversation_state={
            "conversation_mode": "conversion",
            "post_purchase_cooldown": True,
        },
    )

    print_result("POST PURCHASE", post_purchase)

    assert (
        post_purchase["pacing_directive"]
        == "post_purchase_decompression"
    )

    print("\n✅ 3D.11.7 PASSED\n")


if __name__ == "__main__":
    run_test()
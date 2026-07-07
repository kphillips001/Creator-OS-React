from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.11.6 RELATIONSHIP MOMENTUM")
    print("====================================\n")

    service = SmoothIntimacyEscalationService()

    base_intimacy = {
        "intimacy_tier": "premium",
        "runtime_mode": "premium_gate",
        "spender_confidence": "high",
    }

    # --------------------------------------------------
    # LOW RELATIONSHIP
    # --------------------------------------------------

    low = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile={
            "purchase_count": 1,
            "tip_count": 0,
            "total_spend": 20,
        },
        conversation_state={
            "conversation_mode": "flirty",
            "buyer_momentum_score": 5,
            "relationship_depth_score": 5,
            "conversation_streak": 1,
            "engagement_depth_score": 5,
        },
    )

    print_result("LOW", low)

    # --------------------------------------------------
    # HIGH RELATIONSHIP
    # --------------------------------------------------

    high = service.build_escalation_profile(
        intimacy_context=base_intimacy,
        spend_profile={
            "purchase_count": 5,
            "tip_count": 5,
            "total_spend": 250,
        },
        conversation_state={
            "conversation_mode": "tension",
            "buyer_momentum_score": 40,
            "relationship_depth_score": 40,
            "conversation_streak": 10,
            "engagement_depth_score": 35,
        },
    )

    print_result("HIGH", high)

    assert (
        "high_relationship_momentum"
        in high["reasons"]
    )

    assert (
        high["explicit_jump_blocked"]
        is False
    )

    print("\n✅ 3D.11.6 PASSED\n")


if __name__ == "__main__":
    run_test()
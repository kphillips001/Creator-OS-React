from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.11.9 PREMIUM SAFEGUARDS")
    print("====================================\n")

    service = SmoothIntimacyEscalationService()

    # --------------------------------------------------
    # LOW RELATIONSHIP GUARD
    # --------------------------------------------------

    low_relationship = (
        service.build_escalation_profile(
            intimacy_context={
                "intimacy_tier": "premium",
                "runtime_mode": "premium_gate",
                "spender_confidence": "high",
            },
            spend_profile={
                "purchase_count": 1,
                "total_spend": 15,
            },
            conversation_state={
                "conversation_mode": "flirty",
                "buyer_momentum_score": 5,
                "relationship_depth_score": 5,
                "engagement_depth_score": 5,
            },
        )
    )

    print_result(
        "LOW RELATIONSHIP",
        low_relationship,
    )

    assert (
        low_relationship[
            "premium_guard_triggered"
        ]
        is True
    )

    # --------------------------------------------------
    # LOW CONFIDENCE GUARD
    # --------------------------------------------------

    low_confidence = (
        service.build_escalation_profile(
            intimacy_context={
                "intimacy_tier": "premium",
                "runtime_mode": "premium_gate",
                "spender_confidence": "low",
            },
            spend_profile={
                "purchase_count": 5,
                "total_spend": 200,
            },
            conversation_state={
                "conversation_mode": "tension",
                "buyer_momentum_score": 50,
                "relationship_depth_score": 50,
                "engagement_depth_score": 50,
            },
        )
    )

    print_result(
        "LOW CONFIDENCE",
        low_confidence,
    )

    assert (
        low_confidence[
            "premium_guard_triggered"
        ]
        is True
    )

    # --------------------------------------------------
    # HEALTHY PREMIUM STATE
    # --------------------------------------------------

    healthy = (
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
                "conversation_mode": "conversion",
                "buyer_momentum_score": 60,
                "relationship_depth_score": 60,
                "engagement_depth_score": 60,
                "conversation_streak": 10,
            },
        )
    )

    print_result(
        "HEALTHY PREMIUM",
        healthy,
    )

    assert (
        healthy[
            "premium_guard_triggered"
        ]
        is False
    )

    print("\n✅ 3D.11.9 PASSED\n")


if __name__ == "__main__":
    run_test()
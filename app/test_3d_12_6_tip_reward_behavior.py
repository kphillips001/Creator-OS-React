from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.12.6 TIP REWARD BEHAVIOR")
    print("====================================\n")

    service = PostPurchaseDecisionService()

    # --------------------------------------------------
    # SMALL TIP
    # --------------------------------------------------

    small_tip = service.decide_next_action(
        event_type="tip_received",
        amount=5,
        buyer_tier="LOW_SPENDER",
        heat_score=45,
        intent_score=40,
        conversation_mode="casual",
    )

    print_result("SMALL TIP", small_tip)

    assert (
        small_tip["next_action"]
        in [
            "tip_reward",
            "soft_continue",
            "thank_you_only",
        ]
    )

    # --------------------------------------------------
    # MEDIUM TIP
    # --------------------------------------------------

    medium_tip = service.decide_next_action(
        event_type="tip_received",
        amount=35,
        buyer_tier="ACTIVE_BUYER",
        heat_score=70,
        intent_score=70,
        conversation_mode="flirty",
    )

    print_result("MEDIUM TIP", medium_tip)

    assert (
        medium_tip["allow_followup"]
        is True
    )

    # --------------------------------------------------
    # LARGE TIP
    # --------------------------------------------------

    large_tip = service.decide_next_action(
        event_type="tip_received",
        amount=150,
        buyer_tier="HIGH_VALUE",
        heat_score=85,
        intent_score=85,
        buyer_session_state={
            "relationship_depth_score": 80,
            "buyer_momentum_score": 85,
            "recent_offer_pressure": 15,
        },
        conversation_mode="flirty",
    )

    print_result("LARGE TIP", large_tip)

    assert (
        large_tip["next_action"]
        in [
            "tip_reward",
            "premium_followup",
            "whale_retention",
        ]
    )

    # --------------------------------------------------
    # REPEAT TIPPER
    # --------------------------------------------------

    repeat_tipper = service.decide_next_action(
        event_type="tip_received",
        amount=60,
        buyer_tier="ACTIVE_BUYER",
        heat_score=80,
        intent_score=80,
        buyer_session_state={
            "relationship_depth_score": 90,
            "buyer_momentum_score": 95,
            "tip_frequency": 10,
            "recent_offer_pressure": 5,
        },
        conversation_mode="flirty",
    )

    print_result("REPEAT TIPPER", repeat_tipper)

    assert (
        repeat_tipper["pacing_profile"]
        in [
            "relationship",
            "premium",
            "active",
            "whale",
        ]
    )

    # --------------------------------------------------
    # OVERPRESSURED TIPPER
    # --------------------------------------------------

    pressured = service.decide_next_action(
        event_type="tip_received",
        amount=100,
        buyer_tier="HIGH_VALUE",
        heat_score=95,
        intent_score=95,
        buyer_session_state={
            "relationship_depth_score": 90,
            "buyer_momentum_score": 90,
            "recent_offer_pressure": 95,
        },
        conversation_mode="conversion",
    )

    print_result("OVERPRESSURED", pressured)

    assert (
        pressured["should_slow_down"]
        is True
    )

    print("\n✅ 3D.12.6 PASSED\n")


if __name__ == "__main__":
    run_test()
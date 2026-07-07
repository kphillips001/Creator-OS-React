from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.12.4 OFFER AGGRESSION PACING")
    print("====================================\n")

    service = PostPurchaseDecisionService()

    # --------------------------------------------------
    # STANDARD
    # --------------------------------------------------

    standard = service.decide_next_action(
        event_type="purchase_received",
        amount=30,
        buyer_tier="ACTIVE_BUYER",
        heat_score=60,
        intent_score=60,
    )

    print_result("STANDARD", standard)

    assert (
        standard["pacing_profile"]
        in ["active", "neutral", "slow"]
    )

    # --------------------------------------------------
    # LARGE PURCHASE
    # --------------------------------------------------

    premium = service.decide_next_action(
        event_type="purchase_received",
        amount=150,
        buyer_tier="HIGH_VALUE",
        heat_score=80,
        intent_score=80,
    )

    print_result("PREMIUM", premium)

    assert (
        premium["pacing_profile"]
        in [
            "premium",
            "casual",
            "slow",
        ]
    )

    # --------------------------------------------------
    # MASSIVE PURCHASE
    # --------------------------------------------------

    whale = service.decide_next_action(
        event_type="purchase_received",
        amount=400,
        buyer_tier="WHALE",
        heat_score=95,
        intent_score=95,
    )

    print_result("WHALE", whale)

    assert (
        whale["pacing_profile"]
        in [
            "whale",
            "casual",
            "slow",
        ]
    )

    assert (
        whale["should_slow_down"]
        is True
    )

    # --------------------------------------------------
    # OFFER PRESSURE
    # --------------------------------------------------

    pressure = service.decide_next_action(
        event_type="purchase_received",
        amount=60,
        buyer_tier="ACTIVE_BUYER",
        heat_score=90,
        intent_score=90,
        buyer_session_state={
            "recent_offer_pressure": 90,
        },
    )

    print_result("PRESSURE", pressure)

    assert (
        pressure["pacing_profile"]
        == "decompression"
    )

    # --------------------------------------------------
    # RELATIONSHIP CONTINUATION
    # --------------------------------------------------

    relationship = service.decide_next_action(
        event_type="purchase_received",
        amount=90,
        buyer_tier="HIGH_VALUE",
        heat_score=80,
        intent_score=80,
        buyer_session_state={
            "relationship_depth_score": 90,
            "buyer_momentum_score": 90,
            "recent_offer_pressure": 10,
        },
        conversation_mode="flirty",
    )

    print_result(
        "RELATIONSHIP",
        relationship,
    )

    assert (
        relationship["pacing_profile"]
        == "relationship"
    )

    print("\n✅ 3D.12.4 PASSED\n")


if __name__ == "__main__":
    run_test()
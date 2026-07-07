from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.12.5 WHALE RETENTION LOGIC")
    print("====================================\n")

    service = PostPurchaseDecisionService()

    # --------------------------------------------------
    # LARGE WHALE PURCHASE
    # --------------------------------------------------

    whale = service.decide_next_action(
        event_type="purchase_received",
        amount=500,
        buyer_tier="WHALE",
        heat_score=90,
        intent_score=90,
        buyer_session_state={
            "relationship_depth_score": 85,
            "buyer_momentum_score": 90,
            "recent_offer_pressure": 15,
        },
        conversation_mode="flirty",
    )

    print_result("WHALE", whale)

    assert (
        whale["next_action"]
        in [
            "whale_retention",
            "premium_followup",
        ]
    )

    # --------------------------------------------------
    # HIGH VALUE RELATIONSHIP
    # --------------------------------------------------

    high_value = service.decide_next_action(
        event_type="purchase_received",
        amount=220,
        buyer_tier="HIGH_VALUE",
        heat_score=80,
        intent_score=80,
        buyer_session_state={
            "relationship_depth_score": 95,
            "buyer_momentum_score": 85,
            "recent_offer_pressure": 10,
        },
        conversation_mode="flirty",
    )

    print_result("HIGH VALUE", high_value)

    assert (
        high_value["pacing_profile"]
        == "relationship"
    )

    # --------------------------------------------------
    # OVERPRESSURED WHALE
    # --------------------------------------------------

    pressure = service.decide_next_action(
        event_type="purchase_received",
        amount=350,
        buyer_tier="WHALE",
        heat_score=95,
        intent_score=95,
        buyer_session_state={
            "relationship_depth_score": 90,
            "buyer_momentum_score": 90,
            "recent_offer_pressure": 95,
        },
        conversation_mode="conversion",
    )

    print_result("PRESSURE", pressure)

    assert (
        pressure["should_slow_down"]
        is True
    )

    assert (
        pressure["pacing_profile"]
        == "decompression"
    )

    # --------------------------------------------------
    # SAFE WHALE CONTINUATION
    # --------------------------------------------------

    continuation = service.decide_next_action(
        event_type="purchase_received",
        amount=275,
        buyer_tier="WHALE",
        heat_score=88,
        intent_score=88,
        buyer_session_state={
            "relationship_depth_score": 95,
            "buyer_momentum_score": 95,
            "recent_offer_pressure": 5,
        },
        conversation_mode="flirty",
    )

    print_result("CONTINUATION", continuation)

    assert (
        continuation["allow_followup"]
        is True
    )

    print("\n✅ 3D.12.5 PASSED\n")


if __name__ == "__main__":
    run_test()
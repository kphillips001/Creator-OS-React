from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.12.7 SUBSCRIPTION WELCOME FLOWS")
    print("====================================\n")

    service = PostPurchaseDecisionService()

    # --------------------------------------------------
    # NEW SUBSCRIBER
    # --------------------------------------------------

    new_subscriber = service.decide_next_action(
        event_type="subscription_created",
        amount=0,
        buyer_tier="LOW_SPENDER",
        heat_score=40,
        intent_score=35,
        conversation_mode="casual",
    )

    print_result("NEW SUBSCRIBER", new_subscriber)

    assert (
        new_subscriber["next_action"]
        == "subscription_welcome"
    )

    assert (
        new_subscriber["should_slow_down"]
        is True
    )

    # --------------------------------------------------
    # RENEWED SUBSCRIBER
    # --------------------------------------------------

    renewed = service.decide_next_action(
        event_type="subscription_renewed",
        amount=0,
        buyer_tier="ACTIVE_BUYER",
        heat_score=65,
        intent_score=60,
        conversation_mode="flirty",
    )

    print_result("RENEWED SUBSCRIBER", renewed)

    assert (
        renewed["next_action"]
        == "subscription_welcome"
    )

    assert (
        renewed["allow_followup"]
        is True
    )

    # --------------------------------------------------
    # HIGH HEAT SUBSCRIBER
    # --------------------------------------------------

    high_heat = service.decide_next_action(
        event_type="subscription_created",
        amount=0,
        buyer_tier="ACTIVE_BUYER",
        heat_score=90,
        intent_score=85,
        buyer_session_state={
            "relationship_depth_score": 75,
            "buyer_momentum_score": 80,
            "recent_offer_pressure": 10,
        },
        conversation_mode="flirty",
    )

    print_result("HIGH HEAT SUBSCRIBER", high_heat)

    assert (
        high_heat["should_escalate"]
        is True
    )

    # --------------------------------------------------
    # HIGH VALUE SUBSCRIBER
    # --------------------------------------------------

    high_value = service.decide_next_action(
        event_type="subscription_created",
        amount=0,
        buyer_tier="HIGH_VALUE",
        heat_score=75,
        intent_score=70,
        buyer_session_state={
            "relationship_depth_score": 85,
            "buyer_momentum_score": 85,
            "recent_offer_pressure": 5,
        },
        conversation_mode="flirty",
    )

    print_result("HIGH VALUE SUBSCRIBER", high_value)

    assert (
        high_value["pacing_profile"]
        in [
            "relationship",
            "active",
            "slow",
        ]
    )

    # --------------------------------------------------
    # SUBSCRIBER WITH OFFER PRESSURE
    # --------------------------------------------------

    pressured = service.decide_next_action(
        event_type="subscription_created",
        amount=0,
        buyer_tier="ACTIVE_BUYER",
        heat_score=90,
        intent_score=90,
        buyer_session_state={
            "recent_offer_pressure": 90,
        },
        conversation_mode="conversion",
    )

    print_result("PRESSURED SUBSCRIBER", pressured)

    assert (
        pressured["should_slow_down"]
        is True
    )

    assert (
        pressured["pacing_profile"]
        == "decompression"
    )

    print("\n✅ 3D.12.7 PASSED\n")


if __name__ == "__main__":
    run_test()
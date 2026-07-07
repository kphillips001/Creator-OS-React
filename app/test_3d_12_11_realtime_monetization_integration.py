from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n==============================")
    print(" 3D.12.11 REALTIME INTEGRATION")
    print("==============================\n")

    service = PostPurchaseDecisionService()

    #
    # PURCHASE EVENT
    #

    purchase = service.decide_next_action(
        event_type="purchase_received",
        amount=60,
        buyer_tier="ACTIVE_BUYER",
        heat_score=85,
        intent_score=85,
        buyer_session_state={
            "buyer_momentum_score": 85,
            "recent_offer_pressure": 15,
        },
        conversation_mode="conversion",
    )

    print_result("PURCHASE", purchase)

    assert (
        purchase["success"]
        is True
    )

    assert (
        purchase["allow_followup"]
        is True
    )

    #
    # TIP EVENT
    #

    tip = service.decide_next_action(
        event_type="tip_received",
        amount=120,
        buyer_tier="HIGH_VALUE",
        heat_score=80,
        intent_score=80,
        buyer_session_state={
            "buyer_momentum_score": 90,
        },
        conversation_mode="flirty",
    )

    print_result("TIP", tip)

    assert (
        tip["next_action"]
        == "tip_reward"
    )

    #
    # SUBSCRIPTION EVENT
    #

    subscription = service.decide_next_action(
        event_type="subscription_created",
        amount=0,
        buyer_tier="LOW_SPENDER",
        heat_score=45,
        intent_score=45,
        buyer_session_state={},
        conversation_mode="casual",
    )

    print_result("SUBSCRIPTION", subscription)

    assert (
        subscription["next_action"]
        == "subscription_welcome"
    )

    #
    # UNLOCK EVENT
    #

    unlock = service.decide_next_action(
        event_type="unlock_confirmed",
        amount=90,
        buyer_tier="HIGH_VALUE",
        heat_score=90,
        intent_score=90,
        buyer_session_state={
            "buyer_momentum_score": 95,
            "relationship_depth_score": 90,
        },
        conversation_mode="flirty",
    )

    print_result("UNLOCK", unlock)

    assert (
        unlock["should_escalate"]
        is True
    )

    #
    # PRESSURE PROTECTION
    #

    pressure = service.decide_next_action(
        event_type="purchase_received",
        amount=250,
        buyer_tier="WHALE",
        heat_score=95,
        intent_score=95,
        buyer_session_state={
            "recent_offer_pressure": 100,
            "recent_purchase_count": 12,
            "cooldown_decay_level": 100,
        },
        conversation_mode="conversion",
    )

    print_result("PRESSURE", pressure)

    assert (
        pressure["ppv_suppressed"]
        is True
    )

    assert (
        pressure["followup_mode"]
        == "deep_cooldown"
    )

    print("\n✅ 3D.12.11 PASSED\n")


if __name__ == "__main__":
    run_test()
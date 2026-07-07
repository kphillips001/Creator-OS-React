from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n==============================")
    print(" 3D.12.10 RUNTIME COOLDOWN")
    print("==============================\n")

    service = PostPurchaseDecisionService()

    #
    # ACTIVE COOLDOWN
    #

    active = service.decide_next_action(
        event_type="purchase_received",
        amount=40,
        buyer_tier="ACTIVE_BUYER",
        heat_score=85,
        intent_score=85,
        buyer_session_state={
            "cooldown_decay_level": 95,
            "recent_offer_pressure": 90,
        },
        conversation_mode="conversion",
    )

    print_result("ACTIVE COOLDOWN", active)

    assert (
        active["ppv_suppressed"]
        is True
    )

    assert (
        active["escalation_paused"]
        is True
    )

    assert (
        active["followup_mode"]
        in [
            "cooldown",
            "deep_cooldown",
        ]
    )

    #
    # HEALTHY ACTIVE BUYER
    #

    healthy = service.decide_next_action(
        event_type="purchase_received",
        amount=75,
        buyer_tier="ACTIVE_BUYER",
        heat_score=80,
        intent_score=80,
        buyer_session_state={
            "cooldown_decay_level": 10,
            "recent_offer_pressure": 10,
            "buyer_momentum_score": 85,
        },
        conversation_mode="flirty",
    )

    print_result("HEALTHY", healthy)

    assert (
        healthy["ppv_suppressed"]
        is False
    )

    assert (
        healthy["escalation_paused"]
        is False
    )

    #
    # WHALE PRESSURE PROTECTION
    #

    whale = service.decide_next_action(
        event_type="purchase_received",
        amount=400,
        buyer_tier="WHALE",
        heat_score=95,
        intent_score=95,
        buyer_session_state={
            "recent_offer_pressure": 95,
            "recent_purchase_count": 8,
        },
        conversation_mode="conversion",
    )

    print_result("WHALE", whale)

    assert (
        whale["ppv_suppressed"]
        is True
    )

    assert (
        whale["should_slow_down"]
        is True
    )

    #
    # POST TIP RECOVERY
    #

    tip = service.decide_next_action(
        event_type="tip_received",
        amount=120,
        buyer_tier="HIGH_VALUE",
        heat_score=75,
        intent_score=75,
        buyer_session_state={
            "cooldown_decay_level": 30,
            "buyer_momentum_score": 90,
        },
        conversation_mode="flirty",
    )

    print_result("TIP RECOVERY", tip)

    assert (
        tip["ppv_suppressed"]
        is False
    )

    assert (
        tip["allow_followup"]
        is True
    )

    #
    # DEEP DECOMPRESSION
    #

    decompression = service.decide_next_action(
        event_type="purchase_received",
        amount=300,
        buyer_tier="HIGH_VALUE",
        heat_score=95,
        intent_score=95,
        buyer_session_state={
            "cooldown_decay_level": 100,
            "recent_offer_pressure": 100,
            "recent_purchase_count": 10,
        },
        conversation_mode="conversion",
    )

    print_result("DECOMPRESSION", decompression)

    assert (
        decompression["followup_mode"]
        == "deep_cooldown"
    )

    assert (
        decompression["ppv_suppressed"]
        is True
    )

    print("\n✅ 3D.12.10 PASSED\n")


if __name__ == "__main__":
    run_test()
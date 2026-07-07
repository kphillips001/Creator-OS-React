from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n==============================")
    print(" 3D.12.9 NEXT BEST OFFER")
    print("==============================\n")

    service = PostPurchaseDecisionService()

    #
    # VIP → PREMIUM
    #

    vip = service.decide_next_action(
        event_type="purchase_received",
        amount=40,
        buyer_tier="ACTIVE_BUYER",
        heat_score=80,
        intent_score=80,
        buyer_session_state={
            "last_offer_type": "vip",
        },
        conversation_mode="conversion",
    )

    print_result("VIP", vip)

    assert (
        vip["next_best_offer"]
        == "premium_followup_offer"
    )

    #
    # PREMIUM RETENTION
    #

    retention = service.decide_next_action(
        event_type="purchase_received",
        amount=200,
        buyer_tier="HIGH_VALUE",
        heat_score=90,
        intent_score=90,
        buyer_session_state={
            "recent_purchase_count": 5,
        },
        conversation_mode="flirty",
    )

    print_result("RETENTION", retention)

    assert (
        retention["next_best_offer"]
        in [
            "exclusive_retention_offer",
            "no_offer_cooldown",
        ]
    )

    #
    # HIGH TIP
    #

    tip = service.decide_next_action(
        event_type="tip_received",
        amount=75,
        buyer_tier="ACTIVE_BUYER",
        heat_score=70,
        intent_score=70,
        buyer_session_state={},
        conversation_mode="flirty",
    )

    print_result("TIP", tip)

    assert (
        tip["next_best_offer"]
        == "reward_tease_sequence"
    )

    #
    # SUBSCRIBER
    #

    sub = service.decide_next_action(
        event_type="subscription_created",
        amount=0,
        buyer_tier="LOW_SPENDER",
        heat_score=40,
        intent_score=40,
        buyer_session_state={},
        conversation_mode="casual",
    )

    print_result("SUBSCRIBER", sub)

    assert (
        sub["next_best_offer"]
        == "subscriber_warmup_sequence"
    )

    #
    # COOLDOWN
    #

    cooldown = service.decide_next_action(
        event_type="purchase_received",
        amount=30,
        buyer_tier="ACTIVE_BUYER",
        heat_score=90,
        intent_score=90,
        buyer_session_state={
            "cooldown_decay_level": 90,
        },
        conversation_mode="conversion",
    )

    print_result("COOLDOWN", cooldown)

    assert (
        cooldown["next_best_offer"]
        == "no_offer_cooldown"
    )

    print("\n✅ 3D.12.9 PASSED\n")


if __name__ == "__main__":
    run_test()
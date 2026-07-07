from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.12.8 COOLDOWN FOLLOWUP INTEL")
    print("====================================\n")

    service = PostPurchaseDecisionService()

    # --------------------------------------------------
    # COOLDOWN
    # --------------------------------------------------

    cooldown = service.decide_next_action(
        event_type="purchase_received",
        amount=50,
        buyer_tier="ACTIVE_BUYER",
        heat_score=80,
        intent_score=80,
        buyer_session_state={
            "post_purchase_cooldown": True,
        },
        conversation_mode="flirty",
    )

    print_result("COOLDOWN", cooldown)

    assert (
        cooldown["followup_mode"]
        == "cooldown"
    )

    assert (
        cooldown["ppv_suppressed"]
        is True
    )

    assert (
        cooldown["escalation_paused"]
        is True
    )

    # --------------------------------------------------
    # OFFER PRESSURE
    # --------------------------------------------------

    pressure = service.decide_next_action(
        event_type="purchase_received",
        amount=40,
        buyer_tier="ACTIVE_BUYER",
        heat_score=90,
        intent_score=90,
        buyer_session_state={
            "recent_offer_pressure": 90,
        },
        conversation_mode="conversion",
    )

    print_result("PRESSURE", pressure)

    assert (
        pressure["followup_mode"]
        in [
            "decompression",
            "deep_cooldown",
        ]
    )

    assert (
        pressure["ppv_suppressed"]
        is True
    )

    # --------------------------------------------------
    # MULTIPLE PURCHASES
    # --------------------------------------------------

    multiple_purchases = (
        service.decide_next_action(
            event_type="purchase_received",
            amount=80,
            buyer_tier="HIGH_VALUE",
            heat_score=75,
            intent_score=75,
            buyer_session_state={
                "recent_purchase_count": 3,
            },
            conversation_mode="flirty",
        )
    )

    print_result(
        "MULTIPLE PURCHASES",
        multiple_purchases,
    )

    assert (
        multiple_purchases["followup_mode"]
        == "retention"
    )

    assert (
        multiple_purchases["ppv_suppressed"]
        is True
    )

    # --------------------------------------------------
    # EMOTIONAL CONTINUATION
    # --------------------------------------------------

    emotional = service.decide_next_action(
        event_type="purchase_received",
        amount=60,
        buyer_tier="ACTIVE_BUYER",
        heat_score=75,
        intent_score=75,
        buyer_session_state={
            "relationship_depth_score": 85,
            "buyer_momentum_score": 85,
            "emotional_engagement_score": 90,
            "recent_offer_pressure": 10,
        },
        conversation_mode="flirty",
    )

    print_result(
        "EMOTIONAL CONTINUATION",
        emotional,
    )

    assert (
        emotional["followup_mode"]
        == "emotional_continuation"
    )

    assert (
        emotional["ppv_suppressed"]
        is False
    )

    # --------------------------------------------------
    # DEEP COOLDOWN
    # --------------------------------------------------

    deep_cooldown = service.decide_next_action(
        event_type="purchase_received",
        amount=100,
        buyer_tier="ACTIVE_BUYER",
        heat_score=90,
        intent_score=90,
        buyer_session_state={
            "cooldown_decay_level": 80,
        },
        conversation_mode="conversion",
    )

    print_result(
        "DEEP COOLDOWN",
        deep_cooldown,
    )

    assert (
        deep_cooldown["followup_mode"]
        == "deep_cooldown"
    )

    assert (
        deep_cooldown["escalation_paused"]
        is True
    )

    print("\n✅ 3D.12.8 PASSED\n")


if __name__ == "__main__":
    run_test()
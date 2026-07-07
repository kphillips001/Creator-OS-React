from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.12.2 ROUTING REFINEMENT")
    print("====================================\n")

    service = PostPurchaseDecisionService()

    # --------------------------------------------------
    # WHALE PROTECTION
    # --------------------------------------------------

    whale = service.decide_next_action(
        event_type="purchase_received",
        amount=200,
        buyer_tier="WHALE",
        heat_score=95,
        intent_score=95,
        content_purchased={
            "content_tier": "premium",
        },
        buyer_session_state={
            "relationship_depth_score": 20,
            "buyer_momentum_score": 20,
            "recent_offer_pressure": 50,
        },
    )

    print_result("WHALE PROTECTION", whale)

    assert (
        whale["next_action"]
        == "whale_retention"
    )

    assert whale["should_slow_down"] is True

    # --------------------------------------------------
    # HEALTHY WHALE CONTINUATION
    # --------------------------------------------------

    healthy_whale = (
        service.decide_next_action(
            event_type="purchase_received",
            amount=250,
            buyer_tier="WHALE",
            heat_score=90,
            intent_score=90,
            content_purchased={
                "content_tier": "premium",
            },
            buyer_session_state={
                "relationship_depth_score": 90,
                "buyer_momentum_score": 90,
                "recent_offer_pressure": 10,
            },
        )
    )

    print_result(
        "HEALTHY WHALE",
        healthy_whale,
    )

    assert (
        healthy_whale["next_action"]
        == "premium_followup"
    )

    assert (
        healthy_whale["should_escalate"]
        is True
    )

    # --------------------------------------------------
    # COOLDOWN STATE
    # --------------------------------------------------

    cooldown = (
        service.decide_next_action(
            event_type="purchase_received",
            amount=40,
            buyer_tier="ACTIVE_BUYER",
            buyer_session_state={
                "post_purchase_cooldown": True,
            },
        )
    )

    print_result(
        "COOLDOWN",
        cooldown,
    )

    assert (
        cooldown["should_slow_down"]
        is True
    )

    # --------------------------------------------------
    # HIGH OFFER PRESSURE
    # --------------------------------------------------

    pressure = (
        service.decide_next_action(
            event_type="purchase_received",
            amount=60,
            buyer_tier="ACTIVE_BUYER",
            heat_score=95,
            intent_score=95,
            buyer_session_state={
                "recent_offer_pressure": 95,
            },
        )
    )

    print_result(
        "HIGH PRESSURE",
        pressure,
    )

    assert (
        pressure["aggression_level"]
        == "low"
    )

    print("\n✅ 3D.12.2 PASSED\n")


if __name__ == "__main__":
    run_test()
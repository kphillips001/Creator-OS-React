from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.12.3 BUYER TIER SHAPING")
    print("====================================\n")

    service = PostPurchaseDecisionService()

    # --------------------------------------------------
    # NON BUYER
    # --------------------------------------------------

    non_buyer = service.decide_next_action(
        event_type="purchase_received",
        amount=5,
        buyer_tier="NON_BUYER",
        heat_score=95,
        intent_score=95,
    )

    print_result("NON BUYER", non_buyer)

    assert (
        non_buyer["aggression_level"]
        == "low"
    )

    assert (
        non_buyer["should_escalate"]
        is False
    )

    # --------------------------------------------------
    # LOW SPENDER
    # --------------------------------------------------

    low_spender = service.decide_next_action(
        event_type="purchase_received",
        amount=15,
        buyer_tier="LOW_SPENDER",
        heat_score=75,
        intent_score=75,
    )

    print_result(
        "LOW SPENDER",
        low_spender,
    )

    assert (
        low_spender["should_slow_down"]
        is True
    )

    # --------------------------------------------------
    # ACTIVE BUYER
    # --------------------------------------------------

    active = service.decide_next_action(
        event_type="purchase_received",
        amount=45,
        buyer_tier="ACTIVE_BUYER",
        heat_score=70,
        intent_score=70,
    )

    print_result(
        "ACTIVE BUYER",
        active,
    )

    assert (
        active["should_escalate"]
        is True
    )

    # --------------------------------------------------
    # HIGH VALUE
    # --------------------------------------------------

    high_value = service.decide_next_action(
        event_type="purchase_received",
        amount=90,
        buyer_tier="HIGH_VALUE",
        heat_score=60,
        intent_score=60,
        buyer_session_state={
            "relationship_depth_score": 70,
        },
    )

    print_result(
        "HIGH VALUE",
        high_value,
    )

    assert (
        high_value["should_escalate"]
        is True
    )

    # --------------------------------------------------
    # WHALE PROTECTION
    # --------------------------------------------------

    whale = service.decide_next_action(
        event_type="purchase_received",
        amount=200,
        buyer_tier="WHALE",
        heat_score=90,
        intent_score=90,
        buyer_session_state={
            "relationship_depth_score": 40,
            "recent_offer_pressure": 80,
        },
    )

    print_result(
        "WHALE PROTECTION",
        whale,
    )

    assert (
        whale["should_slow_down"]
        is True
    )

    assert (
        whale["aggression_level"]
        == "low"
    )

    # --------------------------------------------------
    # HEALTHY WHALE
    # --------------------------------------------------

    healthy_whale = (
        service.decide_next_action(
            event_type="purchase_received",
            amount=300,
            buyer_tier="WHALE",
            heat_score=90,
            intent_score=90,
            buyer_session_state={
                "relationship_depth_score": 95,
                "recent_offer_pressure": 10,
            },
        )
    )

    print_result(
        "HEALTHY WHALE",
        healthy_whale,
    )

    assert (
        healthy_whale["should_escalate"]
        is True
    )

    print("\n✅ 3D.12.3 PASSED\n")


if __name__ == "__main__":
    run_test()
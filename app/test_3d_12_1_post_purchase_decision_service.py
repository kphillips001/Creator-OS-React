from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.12.1 POST-PURCHASE DECISION")
    print("====================================\n")

    service = PostPurchaseDecisionService()

    vip_purchase = service.decide_next_action(
        event_type="purchase_received",
        amount=29.99,
        buyer_tier="ACTIVE_BUYER",
        heat_score=70,
        intent_score=70,
        content_purchased={
            "content_tier": "vip",
        },
        conversation_mode="tension",
    )

    print_result("VIP PURCHASE", vip_purchase)

    assert vip_purchase["success"] is True
    assert vip_purchase["next_action"] == "vip_to_premium_upsell"
    assert vip_purchase["should_escalate"] is True

    premium_purchase = service.decide_next_action(
        event_type="unlock_confirmed",
        amount=99.99,
        buyer_tier="ACTIVE_BUYER",
        content_purchased={
            "content_tier": "premium",
        },
        conversation_mode="conversion",
    )

    print_result("PREMIUM PURCHASE", premium_purchase)

    assert premium_purchase["next_action"] == "premium_followup"
    assert premium_purchase["should_slow_down"] is True

    whale_purchase = service.decide_next_action(
        event_type="purchase_received",
        amount=199.99,
        buyer_tier="WHALE",
        heat_score=90,
        intent_score=90,
        content_purchased={
            "content_tier": "premium",
        },
        conversation_mode="conversion",
    )

    print_result("WHALE PURCHASE", whale_purchase)

    assert whale_purchase["next_action"] == "whale_retention"

    tip = service.decide_next_action(
        event_type="tip_received",
        amount=75,
        buyer_tier="HIGH_VALUE",
        heat_score=80,
        intent_score=70,
        conversation_mode="flirty",
    )

    print_result("TIP", tip)

    assert tip["next_action"] == "tip_reward"
    assert tip["should_escalate"] is True

    subscription = service.decide_next_action(
        event_type="subscription_created",
        amount=0,
        buyer_tier="LOW_SPENDER",
        conversation_mode="casual",
    )

    print_result("SUBSCRIPTION", subscription)

    assert subscription["next_action"] == "subscription_welcome"

    buyer_session_block = service.decide_next_action(
        event_type="purchase_received",
        amount=50,
        buyer_tier="ACTIVE_BUYER",
        buyer_session_state={
            "buyer_session_active": True,
        },
    )

    print_result("BUYER SESSION BLOCK", buyer_session_block)

    assert buyer_session_block["allow_followup"] is False
    assert buyer_session_block["next_action"] == "thank_you_only"

    print("\n✅ 3D.12.1 PASSED\n")


if __name__ == "__main__":
    run_test()
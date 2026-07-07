from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def validate_result(result):
    assert result["success"] is True
    assert result["next_action"] != ""
    assert result["aggression_level"] in [
        "low",
        "medium",
        "high",
    ]
    assert result["pacing_profile"] != ""
    assert result["followup_mode"] != ""
    assert result["next_best_offer"] is not None
    assert isinstance(result["ppv_suppressed"], bool)
    assert isinstance(result["escalation_paused"], bool)
    assert isinstance(result["allow_followup"], bool)
    assert isinstance(result["reasons"], list)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


def run_test():
    print("\n====================================")
    print(" 3D.12.13 PRODUCTION VALIDATION")
    print("====================================\n")

    service = PostPurchaseDecisionService()

    scenarios = [
        (
            "VIP PURCHASE TO PREMIUM",
            {
                "event_type": "purchase_received",
                "amount": 45,
                "buyer_tier": "ACTIVE_BUYER",
                "heat_score": 85,
                "intent_score": 85,
                "buyer_session_state": {
                    "last_offer_type": "vip",
                    "buyer_momentum_score": 80,
                    "recent_offer_pressure": 10,
                },
                "conversation_mode": "conversion",
            },
        ),
        (
            "PREMIUM UNLOCK",
            {
                "event_type": "unlock_confirmed",
                "amount": 125,
                "buyer_tier": "HIGH_VALUE",
                "heat_score": 90,
                "intent_score": 90,
                "buyer_session_state": {
                    "relationship_depth_score": 90,
                    "buyer_momentum_score": 90,
                    "recent_offer_pressure": 10,
                },
                "conversation_mode": "flirty",
            },
        ),
        (
            "LARGE TIP",
            {
                "event_type": "tip_received",
                "amount": 150,
                "buyer_tier": "HIGH_VALUE",
                "heat_score": 85,
                "intent_score": 80,
                "buyer_session_state": {
                    "relationship_depth_score": 80,
                    "buyer_momentum_score": 85,
                    "recent_offer_pressure": 15,
                },
                "conversation_mode": "flirty",
            },
        ),
        (
            "NEW SUBSCRIBER",
            {
                "event_type": "subscription_created",
                "amount": 0,
                "buyer_tier": "LOW_SPENDER",
                "heat_score": 40,
                "intent_score": 35,
                "buyer_session_state": {},
                "conversation_mode": "casual",
            },
        ),
        (
            "WHALE RETENTION",
            {
                "event_type": "purchase_received",
                "amount": 500,
                "buyer_tier": "WHALE",
                "heat_score": 95,
                "intent_score": 95,
                "buyer_session_state": {
                    "relationship_depth_score": 95,
                    "buyer_momentum_score": 95,
                    "recent_offer_pressure": 10,
                },
                "conversation_mode": "flirty",
            },
        ),
        (
            "HIGH PRESSURE COOLDOWN",
            {
                "event_type": "purchase_received",
                "amount": 250,
                "buyer_tier": "HIGH_VALUE",
                "heat_score": 100,
                "intent_score": 100,
                "buyer_session_state": {
                    "recent_offer_pressure": 100,
                    "cooldown_decay_level": 100,
                    "recent_purchase_count": 5,
                },
                "conversation_mode": "conversion",
            },
        ),
        (
            "BUYER SESSION PROTECTED",
            {
                "event_type": "purchase_received",
                "amount": 200,
                "buyer_tier": "ACTIVE_BUYER",
                "heat_score": 90,
                "intent_score": 90,
                "buyer_session_state": {
                    "buyer_session_active": True,
                },
                "conversation_mode": "conversion",
            },
        ),
    ]

    for title, kwargs in scenarios:
        result = service.decide_next_action(**kwargs)
        print_result(title, result)
        validate_result(result)

    cooldown = service.decide_next_action(
        event_type="purchase_received",
        amount=300,
        buyer_tier="WHALE",
        heat_score=100,
        intent_score=100,
        buyer_session_state={
            "recent_offer_pressure": 100,
            "cooldown_decay_level": 100,
            "recent_purchase_count": 10,
        },
        conversation_mode="conversion",
    )

    print_result("ASSERT COOLDOWN SAFETY", cooldown)

    assert cooldown["ppv_suppressed"] is True
    assert cooldown["escalation_paused"] is True
    assert cooldown["next_best_offer"] == "no_offer_cooldown"

    subscriber = service.decide_next_action(
        event_type="subscription_created",
        amount=0,
        buyer_tier="LOW_SPENDER",
        heat_score=35,
        intent_score=30,
        buyer_session_state={},
        conversation_mode="casual",
    )

    print_result("ASSERT SUBSCRIBER WELCOME", subscriber)

    assert subscriber["next_action"] == "subscription_welcome"
    assert subscriber["next_best_offer"] == "subscriber_warmup_sequence"

    tip = service.decide_next_action(
        event_type="tip_received",
        amount=75,
        buyer_tier="ACTIVE_BUYER",
        heat_score=70,
        intent_score=70,
        buyer_session_state={},
        conversation_mode="flirty",
    )

    print_result("ASSERT TIP SEQUENCE", tip)

    assert tip["next_action"] == "tip_reward"
    assert tip["next_best_offer"] == "reward_tease_sequence"

    print("\n✅ 3D.12.13 PASSED\n")


if __name__ == "__main__":
    run_test()
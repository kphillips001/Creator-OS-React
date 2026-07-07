from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)


def print_result(title, result):
    print(f"\n--- {title} ---")
    print(result)


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
    assert isinstance(result["reasons"], list)


def run_test():
    print("\n====================================")
    print(" 3D.12.12 STRESS EDGE VALIDATION")
    print("====================================\n")

    service = PostPurchaseDecisionService()

    cases = [
        (
            "MASSIVE WHALE SPEND",
            {
                "event_type": "purchase_received",
                "amount": 2000,
                "buyer_tier": "WHALE",
                "heat_score": 100,
                "intent_score": 100,
                "buyer_session_state": {
                    "recent_offer_pressure": 10,
                    "relationship_depth_score": 95,
                    "buyer_momentum_score": 95,
                },
                "conversation_mode": "conversion",
            },
        ),
        (
            "REPEATED UNLOCK BURST",
            {
                "event_type": "unlock_confirmed",
                "amount": 80,
                "buyer_tier": "ACTIVE_BUYER",
                "heat_score": 85,
                "intent_score": 85,
                "buyer_session_state": {
                    "recent_unlock_count": 5,
                    "recent_offer_pressure": 30,
                },
                "conversation_mode": "flirty",
            },
        ),
        (
            "EXTREME PRESSURE SUPPRESSION",
            {
                "event_type": "purchase_received",
                "amount": 150,
                "buyer_tier": "HIGH_VALUE",
                "heat_score": 100,
                "intent_score": 100,
                "buyer_session_state": {
                    "recent_offer_pressure": 100,
                    "cooldown_decay_level": 90,
                },
                "conversation_mode": "conversion",
            },
        ),
        (
            "HIGH HEAT LOW TRUST",
            {
                "event_type": "purchase_received",
                "amount": 20,
                "buyer_tier": "NON_BUYER",
                "heat_score": 100,
                "intent_score": 100,
                "buyer_session_state": {},
                "conversation_mode": "conversion",
            },
        ),
        (
            "HIGH TRUST LOW HEAT",
            {
                "event_type": "purchase_received",
                "amount": 120,
                "buyer_tier": "HIGH_VALUE",
                "heat_score": 25,
                "intent_score": 20,
                "buyer_session_state": {
                    "relationship_depth_score": 90,
                    "buyer_momentum_score": 80,
                    "recent_offer_pressure": 10,
                },
                "conversation_mode": "flirty",
            },
        ),
        (
            "REPEATED TIP CHAIN",
            {
                "event_type": "tip_received",
                "amount": 75,
                "buyer_tier": "ACTIVE_BUYER",
                "heat_score": 85,
                "intent_score": 80,
                "buyer_session_state": {
                    "recent_tip_count": 8,
                    "relationship_depth_score": 85,
                    "buyer_momentum_score": 90,
                },
                "conversation_mode": "flirty",
            },
        ),
        (
            "ACTIVE COOLDOWN RECOVERY",
            {
                "event_type": "purchase_received",
                "amount": 60,
                "buyer_tier": "ACTIVE_BUYER",
                "heat_score": 80,
                "intent_score": 80,
                "buyer_session_state": {
                    "post_purchase_cooldown": True,
                    "cooldown_decay_level": 75,
                },
                "conversation_mode": "flirty",
            },
        ),
        (
            "BUYER SESSION PROTECTED",
            {
                "event_type": "purchase_received",
                "amount": 300,
                "buyer_tier": "WHALE",
                "heat_score": 100,
                "intent_score": 100,
                "buyer_session_state": {
                    "buyer_session_active": True,
                },
                "conversation_mode": "conversion",
            },
        ),
    ]

    for title, kwargs in cases:
        result = service.decide_next_action(**kwargs)
        print_result(title, result)
        validate_result(result)

    pressure = service.decide_next_action(
        event_type="purchase_received",
        amount=250,
        buyer_tier="HIGH_VALUE",
        heat_score=100,
        intent_score=100,
        buyer_session_state={
            "recent_offer_pressure": 100,
            "cooldown_decay_level": 100,
        },
        conversation_mode="conversion",
    )

    print_result("ASSERT PRESSURE SAFETY", pressure)

    assert pressure["ppv_suppressed"] is True
    assert pressure["escalation_paused"] is True
    assert pressure["next_best_offer"] == "no_offer_cooldown"

    whale = service.decide_next_action(
        event_type="purchase_received",
        amount=1000,
        buyer_tier="WHALE",
        heat_score=100,
        intent_score=100,
        buyer_session_state={
            "recent_offer_pressure": 95,
            "recent_purchase_count": 10,
        },
        conversation_mode="conversion",
    )

    print_result("ASSERT WHALE PROTECTION", whale)

    assert whale["should_slow_down"] is True
    assert whale["aggression_level"] == "low"
    assert whale["ppv_suppressed"] is True

    print("\n✅ 3D.12.12 PASSED\n")


if __name__ == "__main__":
    run_test()
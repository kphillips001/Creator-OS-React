from app.services.emotional_presence_refinement_service import (
    EmotionalPresenceRefinementService,
)


def print_header(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def print_result(result: dict):
    for key, value in result.items():
        print(f"{key}: {value}")


def main():
    service = EmotionalPresenceRefinementService()

    print_header("TEST 1 — ACTIVE WHALE HIGH TOUCH PRESENCE")

    result = service.build_emotional_presence_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "user_value_tier": "WHALE",
            "is_whale": True,
            "heat_score": 75,
        },
        conversation_state={
            "conversation_mode": "tension",
            "intent_score": 45,
            "heat_score": 75,
        },
        whale_retention_profile={
            "whale_retention_mode": "active_whale_retention",
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "emotional_familiarity_level": "very_high",
            "intimacy_continuity_strength": "very_strong",
            "relationship_attachment_mode": (
                "premium_emotional_attachment"
            ),
            "emotional_presence_bias": "high_touch_premium_presence",
            "continuity_reinforcement_mode": (
                "active_whale_continuity"
            ),
        },
    )

    print_result(result)

    print_header("TEST 2 — DORMANT WHALE REWARM PRESENCE")

    result = service.build_emotional_presence_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "is_whale": True,
            "heat_score": 10,
        },
        conversation_state={
            "conversation_mode": "casual",
            "intent_score": 12,
            "heat_score": 10,
        },
        whale_retention_profile={
            "whale_retention_mode": "dormant_whale_rewarm",
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "emotional_familiarity_level": "high",
            "intimacy_continuity_strength": "strong",
            "relationship_attachment_mode": (
                "premium_emotional_attachment"
            ),
            "emotional_presence_bias": "familiar_rewarm_presence",
            "continuity_reinforcement_mode": "rewarm_familiarity",
        },
    )

    print_result(result)

    print_header("TEST 3 — HIGH VALUE SOFT PREMIUM PRESENCE")

    result = service.build_emotional_presence_profile(
        buyer_memory={
            "buyer_tier": "HIGH_VALUE",
            "user_value_tier": "HIGH_VALUE",
            "heat_score": 35,
        },
        conversation_state={
            "conversation_mode": "flirty",
            "intent_score": 40,
            "heat_score": 35,
        },
        whale_retention_profile={
            "whale_retention_mode": "high_value_retention",
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "emotional_familiarity_level": "high",
            "intimacy_continuity_strength": "moderate",
            "relationship_attachment_mode": (
                "subscriber_loyalty_attachment"
            ),
            "emotional_presence_bias": "warm_premium_presence",
            "continuity_reinforcement_mode": "premium_familiarity",
        },
    )

    print_result(result)

    print_header("TEST 4 — REACTIVATED WHALE RECOVERY")

    result = service.build_emotional_presence_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "is_whale": True,
            "heat_score": 65,
        },
        conversation_state={
            "conversation_mode": "tension",
            "intent_score": 55,
            "heat_score": 65,
        },
        whale_retention_profile={
            "whale_retention_mode": "reactivated_whale_recovery",
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "emotional_familiarity_level": "very_high",
            "intimacy_continuity_strength": "strong",
            "relationship_attachment_mode": (
                "premium_emotional_attachment"
            ),
            "emotional_presence_bias": "premium_recovery_presence",
            "continuity_reinforcement_mode": (
                "restore_premium_continuity"
            ),
        },
    )

    print_result(result)

    print_header("TEST 5 — NON BUYER SAFE DEFAULT")

    result = service.build_emotional_presence_profile(
        buyer_memory={
            "buyer_tier": "NON_BUYER",
            "total_spend": 0,
            "heat_score": 20,
        },
        conversation_state={
            "conversation_mode": "casual",
            "intent_score": 10,
            "heat_score": 20,
        },
        whale_retention_profile={},
        premium_relationship_memory_profile={},
    )

    print_result(result)

    print("\n" + "=" * 70)
    print("3D.20.3 TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
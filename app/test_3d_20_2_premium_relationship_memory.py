from app.services.premium_relationship_memory_service import (
    PremiumRelationshipMemoryService,
)


def print_header(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def print_result(result: dict):
    for key, value in result.items():
        print(f"{key}: {value}")


def main():
    service = PremiumRelationshipMemoryService()

    print_header("TEST 1 — ACTIVE WHALE WITH DEEP HISTORY")

    result = service.build_relationship_memory_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "user_value_tier": "WHALE",
            "is_whale": True,
            "total_spend": 2500,
            "purchase_count": 18,
            "conversation_streak": 28,
            "engagement_depth_score": 35,
            "relationship_depth_score": 60,
            "buyer_momentum_score": 40,
            "preferred_intensity_score": 8,
            "last_user_message": "I missed this vibe with you",
            "last_bot_response": "Mmm I like when you come back like this 💋",
        },
        conversation_state={
            "conversation_mode": "tension",
            "intent_score": 70,
        },
        whale_retention_profile={
            "whale_retention_mode": "active_whale_retention",
            "emotional_priority_level": "very_high",
        },
    )

    print_result(result)

    print_header("TEST 2 — HIGH VALUE SOFT EMOTIONAL STYLE")

    result = service.build_relationship_memory_profile(
        buyer_memory={
            "buyer_tier": "HIGH_VALUE",
            "total_spend": 450,
            "purchase_count": 6,
            "conversation_streak": 12,
            "engagement_depth_score": 16,
            "relationship_depth_score": 28,
            "buyer_momentum_score": 10,
            "preferred_intensity_score": 2,
            "subscriber_profile": "HIGH_VALUE_SUBSCRIBER",
        },
        conversation_state={
            "conversation_mode": "flirty",
            "intent_score": 45,
        },
        whale_retention_profile={
            "whale_retention_mode": "high_value_retention",
            "emotional_priority_level": "high",
        },
    )

    print_result(result)

    print_header("TEST 3 — DORMANT WHALE REWARM")

    result = service.build_relationship_memory_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "is_whale": True,
            "total_spend": 3100,
            "purchase_count": 24,
            "conversation_streak": 4,
            "engagement_depth_score": 5,
            "relationship_depth_score": 35,
            "buyer_momentum_score": 5,
        },
        conversation_state={
            "conversation_mode": "casual",
            "intent_score": 15,
        },
        whale_retention_profile={
            "whale_retention_mode": "dormant_whale_rewarm",
            "emotional_priority_level": "very_high",
        },
    )

    print_result(result)

    print_header("TEST 4 — NON BUYER SAFE DEFAULT")

    result = service.build_relationship_memory_profile(
        buyer_memory={
            "buyer_tier": "NON_BUYER",
            "total_spend": 0,
            "purchase_count": 0,
            "conversation_streak": 2,
        },
        conversation_state={
            "conversation_mode": "casual",
            "intent_score": 10,
        },
        whale_retention_profile={},
    )

    print_result(result)

    print("\n" + "=" * 70)
    print("3D.20.2 TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
from app.services.premium_conversation_continuity_service import (
    PremiumConversationContinuityService,
)


def print_header(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def print_result(result: dict):
    for key, value in result.items():
        print(f"{key}: {value}")


def main():
    service = PremiumConversationContinuityService()

    print_header("TEST 1 — ACTIVE WHALE CONTINUITY")

    result = service.build_continuity_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "user_value_tier": "WHALE",
            "is_whale": True,
            "offers_shown_count": 1,
            "messages_since_last_offer": 4,
            "post_offer_nudge_count": 0,
            "last_route": "chat",
        },
        conversation_state={
            "conversation_mode": "tension",
            "intent_score": 55,
            "heat_score": 70,
        },
        whale_retention_profile={
            "whale_retention_mode": "active_whale_retention",
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "intimacy_continuity_strength": "very_strong",
            "relationship_attachment_mode": (
                "premium_emotional_attachment"
            ),
        },
        emotional_presence_profile={
            "emotional_presence_mode": (
                "high_touch_premium_presence"
            ),
            "pacing_style": "slow_premium",
            "emotional_rhythm_style": (
                "continuous_relationship_rhythm"
            ),
        },
    )

    print_result(result)

    print_header("TEST 2 — DORMANT WHALE REWARM CONTINUITY")

    result = service.build_continuity_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "is_whale": True,
            "offers_shown_count": 0,
            "messages_since_last_offer": 10,
            "post_offer_nudge_count": 0,
            "last_route": "chat",
        },
        conversation_state={
            "conversation_mode": "casual",
            "intent_score": 15,
            "heat_score": 10,
        },
        whale_retention_profile={
            "whale_retention_mode": "dormant_whale_rewarm",
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "intimacy_continuity_strength": "strong",
            "relationship_attachment_mode": (
                "premium_emotional_attachment"
            ),
        },
        emotional_presence_profile={
            "emotional_presence_mode": "familiar_rewarm_presence",
            "pacing_style": "relationship_first_slow",
            "emotional_rhythm_style": (
                "continuous_relationship_rhythm"
            ),
        },
    )

    print_result(result)

    print_header("TEST 3 — REPEATED CTA PRESSURE SUPPRESSION")

    result = service.build_continuity_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "is_whale": True,
            "offers_shown_count": 4,
            "messages_since_last_offer": 1,
            "post_offer_nudge_count": 2,
            "last_route": "sales",
        },
        conversation_state={
            "conversation_mode": "tension",
            "intent_score": 45,
            "heat_score": 65,
        },
        whale_retention_profile={
            "whale_retention_mode": "active_whale_retention",
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "intimacy_continuity_strength": "strong",
            "relationship_attachment_mode": (
                "premium_emotional_attachment"
            ),
        },
        emotional_presence_profile={
            "emotional_presence_mode": (
                "high_touch_premium_presence"
            ),
            "pacing_style": "slow_premium",
            "emotional_rhythm_style": "standard",
        },
    )

    print_result(result)

    print_header("TEST 4 — HIGH VALUE CONTINUITY")

    result = service.build_continuity_profile(
        buyer_memory={
            "buyer_tier": "HIGH_VALUE",
            "user_value_tier": "HIGH_VALUE",
            "offers_shown_count": 1,
            "messages_since_last_offer": 3,
            "post_offer_nudge_count": 0,
            "last_route": "chat",
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
            "intimacy_continuity_strength": "moderate",
            "relationship_attachment_mode": (
                "subscriber_loyalty_attachment"
            ),
        },
        emotional_presence_profile={
            "emotional_presence_mode": "warm_premium_presence",
            "pacing_style": "careful_premium",
            "emotional_rhythm_style": "standard",
        },
    )

    print_result(result)

    print_header("TEST 5 — NON BUYER SAFE DEFAULT")

    result = service.build_continuity_profile(
        buyer_memory={
            "buyer_tier": "NON_BUYER",
            "offers_shown_count": 0,
        },
        conversation_state={
            "conversation_mode": "casual",
            "intent_score": 10,
            "heat_score": 10,
        },
        whale_retention_profile={},
        premium_relationship_memory_profile={},
        emotional_presence_profile={},
    )

    print_result(result)

    print("\n" + "=" * 70)
    print("3D.20.4 TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
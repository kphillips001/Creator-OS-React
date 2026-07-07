from app.services.whale_burnout_prevention_service import (
    WhaleBurnoutPreventionService,
)


def print_header(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def print_result(result: dict):
    for key, value in result.items():
        print(f"{key}: {value}")


def main():
    service = WhaleBurnoutPreventionService()

    print_header("TEST 1 — WHALE HIGH BURNOUT RISK")

    result = service.build_burnout_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "user_value_tier": "WHALE",
            "is_whale": True,
            "offers_shown_count": 5,
            "post_offer_nudge_count": 3,
            "messages_since_last_offer": 1,
            "engagement_depth_score": 3,
            "conversation_streak": 18,
            "last_route": "sales",
            "offer_state": "nudged",
        },
        conversation_state={
            "conversation_mode": "tension",
            "intent_score": 25,
            "heat_score": 35,
        },
        whale_retention_profile={
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "emotional_familiarity_level": "very_high",
        },
        emotional_presence_profile={
            "emotional_presence_mode": "high_touch_premium_presence",
        },
        premium_conversation_continuity_profile={
            "continuity_cta_suppression": "high",
            "relationship_progression_mode": "immersive_continuity",
        },
    )

    print_result(result)

    print_header("TEST 2 — WHALE MEDIUM BURNOUT RISK")

    result = service.build_burnout_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "is_whale": True,
            "offers_shown_count": 2,
            "post_offer_nudge_count": 1,
            "messages_since_last_offer": 2,
            "engagement_depth_score": 10,
            "conversation_streak": 12,
            "last_content_outcome": "ignored",
            "last_route": "chat",
            "offer_state": "none",
        },
        conversation_state={
            "conversation_mode": "flirty",
            "intent_score": 38,
            "heat_score": 42,
        },
        whale_retention_profile={
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "emotional_familiarity_level": "high",
        },
        emotional_presence_profile={
            "emotional_presence_mode": "warm_premium_presence",
        },
        premium_conversation_continuity_profile={
            "continuity_cta_suppression": "medium",
            "relationship_progression_mode": "moderate_continuity",
        },
    )

    print_result(result)

    print_header("TEST 3 — ACTIVE WHALE LOW BURNOUT RISK")

    result = service.build_burnout_profile(
        buyer_memory={
            "buyer_tier": "WHALE",
            "is_whale": True,
            "offers_shown_count": 0,
            "post_offer_nudge_count": 0,
            "messages_since_last_offer": 8,
            "engagement_depth_score": 22,
            "conversation_streak": 9,
            "last_route": "chat",
            "offer_state": "none",
        },
        conversation_state={
            "conversation_mode": "tension",
            "intent_score": 65,
            "heat_score": 75,
        },
        whale_retention_profile={
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "emotional_familiarity_level": "very_high",
        },
        emotional_presence_profile={
            "emotional_presence_mode": "high_touch_premium_presence",
        },
        premium_conversation_continuity_profile={
            "continuity_cta_suppression": "medium",
            "relationship_progression_mode": "immersive_continuity",
        },
    )

    print_result(result)

    print_header("TEST 4 — HIGH VALUE USER CTA FATIGUE")

    result = service.build_burnout_profile(
        buyer_memory={
            "buyer_tier": "HIGH_VALUE",
            "user_value_tier": "HIGH_VALUE",
            "offers_shown_count": 4,
            "post_offer_nudge_count": 1,
            "messages_since_last_offer": 1,
            "engagement_depth_score": 8,
            "conversation_streak": 16,
            "last_route": "sales",
            "offer_state": "offered",
        },
        conversation_state={
            "conversation_mode": "tension",
            "intent_score": 42,
            "heat_score": 50,
        },
        whale_retention_profile={
            "reduce_sales_pressure": True,
        },
        premium_relationship_memory_profile={
            "emotional_familiarity_level": "high",
        },
        emotional_presence_profile={
            "emotional_presence_mode": "warm_premium_presence",
        },
        premium_conversation_continuity_profile={
            "continuity_cta_suppression": "high",
            "relationship_progression_mode": "moderate_continuity",
        },
    )

    print_result(result)

    print_header("TEST 5 — NON BUYER SAFE DEFAULT")

    result = service.build_burnout_profile(
        buyer_memory={
            "buyer_tier": "NON_BUYER",
            "offers_shown_count": 10,
            "post_offer_nudge_count": 5,
            "messages_since_last_offer": 0,
        },
        conversation_state={
            "conversation_mode": "casual",
            "intent_score": 10,
            "heat_score": 10,
        },
        whale_retention_profile={},
        premium_relationship_memory_profile={},
        emotional_presence_profile={},
        premium_conversation_continuity_profile={},
    )

    print_result(result)

    print("\n" + "=" * 70)
    print("3D.20.5 TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
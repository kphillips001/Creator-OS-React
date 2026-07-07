def should_send_offer(
    subscriber_engagement_mode: str,
    engagement_depth_score: int,
    conversation_streak: int,
    messages_since_last_offer: int,
    offers_shown_count: int,
) -> bool:
    """
    7C.3 — Mode + depth + offer pressure monetization gating

    casual  = no selling
    flirty  = no direct selling yet
    tension = eligible only if:
      - depth is strong enough
      - streak is strong enough
      - enough messages since last offer
      - offer count is not too high
    """

    if subscriber_engagement_mode != "tension":
        return False

    minimum_depth_score = 5
    minimum_streak = 4
    minimum_messages_since_last_offer = 3
    max_offers_shown = 3

    if engagement_depth_score < minimum_depth_score:
        return False

    if conversation_streak < minimum_streak:
        return False

    if messages_since_last_offer < minimum_messages_since_last_offer:
        return False

    if offers_shown_count >= max_offers_shown:
        return False

    return True


if __name__ == "__main__":
    test_cases = [
        {
            "name": "CASUAL never sells",
            "mode": "casual",
            "depth": 10,
            "streak": 10,
            "messages_since_last_offer": 10,
            "offers_shown_count": 0,
            "expected": False,
        },
        {
            "name": "FLIRTY never direct sells",
            "mode": "flirty",
            "depth": 10,
            "streak": 10,
            "messages_since_last_offer": 10,
            "offers_shown_count": 0,
            "expected": False,
        },
        {
            "name": "TENSION blocked when depth too low",
            "mode": "tension",
            "depth": 2,
            "streak": 5,
            "messages_since_last_offer": 10,
            "offers_shown_count": 0,
            "expected": False,
        },
        {
            "name": "TENSION blocked when streak too low",
            "mode": "tension",
            "depth": 6,
            "streak": 2,
            "messages_since_last_offer": 10,
            "offers_shown_count": 0,
            "expected": False,
        },
        {
            "name": "TENSION blocked when too soon after last offer",
            "mode": "tension",
            "depth": 6,
            "streak": 5,
            "messages_since_last_offer": 1,
            "offers_shown_count": 0,
            "expected": False,
        },
        {
            "name": "TENSION blocked when offer count is maxed",
            "mode": "tension",
            "depth": 6,
            "streak": 5,
            "messages_since_last_offer": 5,
            "offers_shown_count": 3,
            "expected": False,
        },
        {
            "name": "TENSION allowed when all conditions are strong",
            "mode": "tension",
            "depth": 6,
            "streak": 5,
            "messages_since_last_offer": 4,
            "offers_shown_count": 2,
            "expected": True,
        },
    ]

    for case in test_cases:
        send_offer = should_send_offer(
            case["mode"],
            case["depth"],
            case["streak"],
            case["messages_since_last_offer"],
            case["offers_shown_count"],
        )

        print("\n==============================")
        print(case["name"])
        print("==============================")
        print(
            f"mode={case['mode']} | depth={case['depth']} | "
            f"streak={case['streak']} | "
            f"messages_since_last_offer={case['messages_since_last_offer']} | "
            f"offers_shown_count={case['offers_shown_count']} | "
            f"send_offer={send_offer}"
        )

        assert send_offer == case["expected"], (
            f"FAILED: {case['name']} expected {case['expected']} "
            f"but got {send_offer}"
        )

    print("\n✅ 7C.3 PASSED — offer pressure prevents over-selling")
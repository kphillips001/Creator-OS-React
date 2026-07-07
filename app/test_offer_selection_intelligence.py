def select_offer_type(
    subscriber_engagement_mode: str,
    buyer_tier: str,
    intent_score: int,
    offers_shown_count: int,
) -> str:
    """
    7D.1 — Basic offer selection intelligence

    Only tension mode can receive offers.
    Offer type is selected based on buyer tier + intent.
    """

    if subscriber_engagement_mode != "tension":
        return "none"

    if offers_shown_count >= 3:
        return "none"

    if buyer_tier == "hot" or intent_score >= 80:
        return "premium"

    if buyer_tier == "warm" or intent_score >= 50:
        return "vip"

    return "tease"


if __name__ == "__main__":
    test_cases = [
        {
            "name": "CASUAL gets no offer",
            "mode": "casual",
            "buyer_tier": "hot",
            "intent_score": 90,
            "offers_shown_count": 0,
            "expected": "none",
        },
        {
            "name": "FLIRTY gets no direct offer",
            "mode": "flirty",
            "buyer_tier": "hot",
            "intent_score": 90,
            "offers_shown_count": 0,
            "expected": "none",
        },
        {
            "name": "TENSION cold user gets tease",
            "mode": "tension",
            "buyer_tier": "cold",
            "intent_score": 25,
            "offers_shown_count": 0,
            "expected": "tease",
        },
        {
            "name": "TENSION warm user gets vip",
            "mode": "tension",
            "buyer_tier": "warm",
            "intent_score": 55,
            "offers_shown_count": 0,
            "expected": "vip",
        },
        {
            "name": "TENSION hot user gets premium",
            "mode": "tension",
            "buyer_tier": "hot",
            "intent_score": 85,
            "offers_shown_count": 0,
            "expected": "premium",
        },
        {
            "name": "Offer blocked when offer count is maxed",
            "mode": "tension",
            "buyer_tier": "hot",
            "intent_score": 90,
            "offers_shown_count": 3,
            "expected": "none",
        },
    ]

    for case in test_cases:
        offer_type = select_offer_type(
            case["mode"],
            case["buyer_tier"],
            case["intent_score"],
            case["offers_shown_count"],
        )

        print("\n==============================")
        print(case["name"])
        print("==============================")
        print(
            f"mode={case['mode']} | buyer_tier={case['buyer_tier']} | "
            f"intent_score={case['intent_score']} | "
            f"offers_shown_count={case['offers_shown_count']} | "
            f"offer_type={offer_type}"
        )

        assert offer_type == case["expected"], (
            f"FAILED: {case['name']} expected {case['expected']} "
            f"but got {offer_type}"
        )

    print("\n✅ 7D.1 PASSED — offer selection chooses correct offer type")
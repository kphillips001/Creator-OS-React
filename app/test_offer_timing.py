# app/test_offer_timing.py

def should_send_offer_with_timing(
    mode: str,
    depth: int,
    streak: int,
    intent_score: int,
    messages_since_last_offer: int,
    offers_shown_count: int,
):
    """
    FINAL timing logic on top of gating.
    """

    # ❌ Never send outside tension
    if mode != "tension":
        return False

    # ❌ Too soon after last offer
    if messages_since_last_offer < 3:
        return False

    # ❌ Too many offers already
    if offers_shown_count >= 3:
        return False

    # 🔥 HIGH INTENT → accelerate
    if intent_score >= 80:
        return True

    # 🔥 MEDIUM INTENT → require decent buildup
    if intent_score >= 50:
        if depth >= 4 and streak >= 3:
            return True
        return False

    # 🔥 LOW INTENT → require strong buildup
    if intent_score >= 20:
        if depth >= 6 and streak >= 5:
            return True
        return False

    # ❌ Very low intent → no selling
    return False


if __name__ == "__main__":

    test_cases = [

        {
            "name": "Not tension → never send",
            "mode": "flirty",
            "depth": 10,
            "streak": 10,
            "intent_score": 90,
            "messages_since_last_offer": 10,
            "offers_shown_count": 0,
            "expected": False,
        },

        {
            "name": "Too soon after last offer",
            "mode": "tension",
            "depth": 6,
            "streak": 5,
            "intent_score": 80,
            "messages_since_last_offer": 1,
            "offers_shown_count": 0,
            "expected": False,
        },

        {
            "name": "Offer count maxed",
            "mode": "tension",
            "depth": 6,
            "streak": 5,
            "intent_score": 80,
            "messages_since_last_offer": 5,
            "offers_shown_count": 3,
            "expected": False,
        },

        {
            "name": "High intent → immediate send",
            "mode": "tension",
            "depth": 1,
            "streak": 1,
            "intent_score": 90,
            "messages_since_last_offer": 5,
            "offers_shown_count": 0,
            "expected": True,
        },

        {
            "name": "Medium intent → needs buildup",
            "mode": "tension",
            "depth": 4,
            "streak": 3,
            "intent_score": 60,
            "messages_since_last_offer": 5,
            "offers_shown_count": 0,
            "expected": True,
        },

        {
            "name": "Medium intent → not enough depth",
            "mode": "tension",
            "depth": 2,
            "streak": 2,
            "intent_score": 60,
            "messages_since_last_offer": 5,
            "offers_shown_count": 0,
            "expected": False,
        },

        {
            "name": "Low intent → requires strong buildup",
            "mode": "tension",
            "depth": 6,
            "streak": 5,
            "intent_score": 25,
            "messages_since_last_offer": 5,
            "offers_shown_count": 0,
            "expected": True,
        },

        {
            "name": "Low intent → not enough buildup",
            "mode": "tension",
            "depth": 3,
            "streak": 2,
            "intent_score": 25,
            "messages_since_last_offer": 5,
            "offers_shown_count": 0,
            "expected": False,
        },
    ]

    print("\n==============================")
    print("TESTING OFFER TIMING")
    print("==============================")

    for case in test_cases:

        result = should_send_offer_with_timing(
            case["mode"],
            case["depth"],
            case["streak"],
            case["intent_score"],
            case["messages_since_last_offer"],
            case["offers_shown_count"],
        )

        print("\n------------------------------")
        print(case["name"])
        print("------------------------------")

        print(
            f"mode={case['mode']} | depth={case['depth']} | streak={case['streak']} | "
            f"intent={case['intent_score']} | since_last={case['messages_since_last_offer']} | "
            f"offers={case['offers_shown_count']} | send={result}"
        )

        if result != case["expected"]:
            print("❌ FAILED")
        else:
            print("✅ PASSED")

    print("\n🎯 7D.4 COMPLETE — timing intelligence working")
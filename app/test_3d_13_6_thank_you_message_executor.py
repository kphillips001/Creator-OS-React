from app.services.thank_you_message_executor_service import (
    ThankYouMessageExecutorService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.6 THANK-YOU MESSAGE EXECUTOR")
    print("======================================\n")

    service = (
        ThankYouMessageExecutorService()
    )

    print("TEST 1 — STANDARD THANK YOU\n")

    result = service.build_thank_you_payload(
        execution_plan={
            "fanvue_user_id": "fan_123",
            "decision_type": "thank_you_only",
            "pacing_profile": "normal",
            "aggression_level": "low",
        },
        spend_profile={
            "buyer_tier": "LOW_SPENDER",
        },
    )

    print(result)

    assert result["success"] is True
    assert (
        result["payload_type"]
        == "thank_you_message"
    )

    print("\nTEST 2 — WHALE STYLE\n")

    result = service.build_thank_you_payload(
        execution_plan={
            "fanvue_user_id": "fan_999",
            "decision_type": "whale_retention",
            "pacing_profile": "premium",
            "aggression_level": "medium",
        },
        spend_profile={
            "buyer_tier": "WHALE",
        },
    )

    print(result)

    assert (
        result["message_style"]
        == "warm_appreciative"
    )

    print("\nTEST 3 — DECOMPRESSION STYLE\n")

    result = service.build_thank_you_payload(
        execution_plan={
            "fanvue_user_id": "fan_777",
            "decision_type": "thank_you_only",
            "pacing_profile": "decompression",
            "aggression_level": "low",
        },
        spend_profile={
            "buyer_tier": "ACTIVE_BUYER",
        },
    )

    print(result)

    assert (
        result["message_style"]
        == "soft_affectionate"
    )

    print("\nTEST 4 — HIGH AGGRESSION\n")

    result = service.build_thank_you_payload(
        execution_plan={
            "fanvue_user_id": "fan_555",
            "decision_type": "premium_followup",
            "pacing_profile": "normal",
            "aggression_level": "high",
        },
        spend_profile={
            "buyer_tier": "HIGH_VALUE",
        },
    )

    print(result)

    assert (
        result["message_style"]
        == "playful_excited"
    )

    print("\nTEST 5 — MISSING USER\n")

    result = service.build_thank_you_payload(
        execution_plan={
            "decision_type": "thank_you_only",
        }
    )

    print(result)

    assert result["success"] is False
    assert (
        result["reason"]
        == "missing_fanvue_user_id"
    )

    print("\n✅ 3D.13.6 PASSED")


if __name__ == "__main__":
    run_test()
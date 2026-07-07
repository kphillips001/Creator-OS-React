from app.services.premium_followup_queue_service import (
    PremiumFollowupQueueService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.9 PREMIUM FOLLOWUP QUEUE")
    print("======================================\n")

    service = (
        PremiumFollowupQueueService()
    )

    print("TEST 1 — STANDARD FOLLOWUP\n")

    result = (
        service.build_followup_queue_payload(
            execution_plan={
                "fanvue_user_id": "fan_123",
                "pacing_profile": "normal",
            },
            spend_profile={
                "buyer_tier": "LOW_SPENDER",
            },
        )
    )

    print(result)

    assert result["success"] is True

    assert (
        result["followup_type"]
        == "light_followup"
    )

    print("\nTEST 2 — PREMIUM BUYER\n")

    result = (
        service.build_followup_queue_payload(
            execution_plan={
                "fanvue_user_id": "fan_456",
                "pacing_profile": "premium",
            },
            spend_profile={
                "buyer_tier": "HIGH_VALUE",
            },
        )
    )

    print(result)

    assert (
        result["followup_type"]
        == "premium_reengagement"
    )

    assert result["delay_minutes"] == 60

    print("\nTEST 3 — WHALE\n")

    result = (
        service.build_followup_queue_payload(
            execution_plan={
                "fanvue_user_id": "fan_whale",
                "pacing_profile": "premium",
            },
            spend_profile={
                "buyer_tier": "WHALE",
            },
        )
    )

    print(result)

    assert (
        result["followup_type"]
        == "vip_continuation"
    )

    assert result["delay_minutes"] == 90

    print("\nTEST 4 — DECOMPRESSION\n")

    result = (
        service.build_followup_queue_payload(
            execution_plan={
                "fanvue_user_id": "fan_soft",
                "pacing_profile": "decompression",
            },
            spend_profile={
                "buyer_tier": "ACTIVE_BUYER",
            },
        )
    )

    print(result)

    assert (
        result["followup_type"]
        == "soft_reengagement"
    )

    print("\nTEST 5 — MISSING EXECUTION PLAN\n")

    result = (
        service.build_followup_queue_payload(
            execution_plan={},
        )
    )

    print(result)

    assert result["success"] is False

    assert (
        result["reason"]
        == "missing_execution_plan"
    )

    print("\n✅ 3D.13.9 PASSED")


if __name__ == "__main__":
    run_test()
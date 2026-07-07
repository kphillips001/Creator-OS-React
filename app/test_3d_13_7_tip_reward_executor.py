from app.services.tip_reward_executor_service import (
    TipRewardExecutorService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.7 TIP REWARD EXECUTOR")
    print("======================================\n")

    service = TipRewardExecutorService()

    print("TEST 1 — LIGHT TIP\n")

    result = service.build_tip_reward_payload(
        execution_plan={
            "fanvue_user_id": "fan_123",
        },
        spend_profile={
            "buyer_tier": "LOW_SPENDER",
        },
        monetization_event={
            "amount": 10,
        },
    )

    print(result)

    assert result["success"] is True
    assert (
        result["reward_level"]
        == "light_reward"
    )

    print("\nTEST 2 — MEDIUM TIP\n")

    result = service.build_tip_reward_payload(
        execution_plan={
            "fanvue_user_id": "fan_456",
        },
        spend_profile={
            "buyer_tier": "ACTIVE_BUYER",
        },
        monetization_event={
            "amount": 50,
        },
    )

    print(result)

    assert (
        result["reward_level"]
        == "medium_reward"
    )

    print("\nTEST 3 — HIGH TIP\n")

    result = service.build_tip_reward_payload(
        execution_plan={
            "fanvue_user_id": "fan_789",
        },
        spend_profile={
            "buyer_tier": "HIGH_VALUE",
        },
        monetization_event={
            "amount": 250,
        },
    )

    print(result)

    assert (
        result["reward_level"]
        == "high_reward"
    )

    print("\nTEST 4 — WHALE\n")

    result = service.build_tip_reward_payload(
        execution_plan={
            "fanvue_user_id": "fan_whale",
        },
        spend_profile={
            "buyer_tier": "WHALE",
        },
        monetization_event={
            "amount": 15,
        },
    )

    print(result)

    assert (
        result["reward_level"]
        == "vip_reward"
    )

    print("\nTEST 5 — MISSING EXECUTION PLAN\n")

    result = service.build_tip_reward_payload(
        execution_plan={},
    )

    print(result)

    assert result["success"] is False
    assert (
        result["reason"]
        == "missing_execution_plan"
    )

    print("\n✅ 3D.13.7 PASSED")


if __name__ == "__main__":
    run_test()
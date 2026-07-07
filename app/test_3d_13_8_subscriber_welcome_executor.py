from app.services.subscriber_welcome_executor_service import (
    SubscriberWelcomeExecutorService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.8 SUBSCRIBER WELCOME EXECUTOR")
    print("======================================\n")

    service = (
        SubscriberWelcomeExecutorService()
    )

    print("TEST 1 — STANDARD SUBSCRIBER\n")

    result = service.build_welcome_payload(
        execution_plan={
            "fanvue_user_id": "fan_123",
        },
        spend_profile={
            "buyer_tier": "NEW_SUBSCRIBER",
        },
        subscription_event={
            "is_returning_subscriber": False,
        },
    )

    print(result)

    assert result["success"] is True

    assert (
        result["welcome_style"]
        == "playful_onboarding"
    )

    print("\nTEST 2 — RETURNING SUBSCRIBER\n")

    result = service.build_welcome_payload(
        execution_plan={
            "fanvue_user_id": "fan_return",
        },
        spend_profile={
            "buyer_tier": "ACTIVE_BUYER",
        },
        subscription_event={
            "is_returning_subscriber": True,
        },
    )

    print(result)

    assert (
        result["welcome_style"]
        == "warm_reunion"
    )

    print("\nTEST 3 — WHALE WELCOME\n")

    result = service.build_welcome_payload(
        execution_plan={
            "fanvue_user_id": "fan_whale",
        },
        spend_profile={
            "buyer_tier": "WHALE",
        },
        subscription_event={
            "is_returning_subscriber": False,
        },
    )

    print(result)

    assert (
        result["welcome_style"]
        == "vip_welcome"
    )

    print("\nTEST 4 — HIGH VALUE\n")

    result = service.build_welcome_payload(
        execution_plan={
            "fanvue_user_id": "fan_high",
        },
        spend_profile={
            "buyer_tier": "HIGH_VALUE",
        },
        subscription_event={
            "is_returning_subscriber": False,
        },
    )

    print(result)

    assert (
        result["onboarding_type"]
        == "premium_path"
    )

    print("\nTEST 5 — MISSING EXECUTION PLAN\n")

    result = service.build_welcome_payload(
        execution_plan={},
    )

    print(result)

    assert result["success"] is False

    assert (
        result["reason"]
        == "missing_execution_plan"
    )

    print("\n✅ 3D.13.8 PASSED")


if __name__ == "__main__":
    run_test()
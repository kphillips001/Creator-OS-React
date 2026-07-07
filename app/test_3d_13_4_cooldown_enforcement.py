from app.services.reaction_cooldown_enforcement_service import (
    ReactionCooldownEnforcementService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.4 COOLDOWN ENFORCEMENT")
    print("======================================\n")

    service = (
        ReactionCooldownEnforcementService()
    )

    print("TEST 1 — STANDARD DELAY\n")

    result = service.evaluate_cooldown(
        execution_plan={
            "decision_type": "thank_you_only",
        },
        spend_profile={
            "buyer_tier": "LOW_SPENDER",
        },
    )

    print(result)

    assert result["success"] is True
    assert result["delay_minutes"] == 15

    print("\nTEST 2 — WHALE DELAY\n")

    result = service.evaluate_cooldown(
        execution_plan={
            "decision_type": "whale_retention",
        },
        spend_profile={
            "buyer_tier": "WHALE",
        },
    )

    print(result)

    assert result["delay_minutes"] == 45
    assert (
        result["cooldown_reason"]
        == "whale_decompression"
    )

    print("\nTEST 3 — PREMIUM PACING\n")

    result = service.evaluate_cooldown(
        execution_plan={
            "decision_type": "premium_followup",
            "pacing_profile": "premium",
        },
        spend_profile={
            "buyer_tier": "ACTIVE_BUYER",
        },
    )

    print(result)

    assert result["delay_minutes"] == 30

    print("\nTEST 4 — DECOMPRESSION\n")

    result = service.evaluate_cooldown(
        execution_plan={
            "decision_type": "thank_you_only",
            "pacing_profile": "decompression",
        },
        spend_profile={
            "buyer_tier": "HIGH_VALUE",
        },
    )

    print(result)

    assert result["delay_minutes"] == 60

    print("\nTEST 5 — SHOULD SLOW DOWN\n")

    result = service.evaluate_cooldown(
        execution_plan={
            "decision_type": "premium_followup",
            "pacing_profile": "premium",
            "should_slow_down": True,
        },
        spend_profile={
            "buyer_tier": "ACTIVE_BUYER",
        },
    )

    print(result)

    assert result["delay_minutes"] == 50

    print("\n✅ 3D.13.4 PASSED")


if __name__ == "__main__":
    run_test()
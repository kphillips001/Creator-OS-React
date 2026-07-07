from app.services.reaction_safety_gate_service import (
    ReactionSafetyGateService,
)


def run_test():
    print("\n====================================")
    print(" 3D.13.2 REACTION SAFETY GATE")
    print("====================================\n")

    service = ReactionSafetyGateService()

    execution_plan = {
        "fanvue_user_id": "fan_123",
        "blocked": False,
    }

    print("TEST 1 — SAFE EXECUTION\n")

    result = service.validate_execution(
        execution_plan=execution_plan,
    )

    print(result)

    assert result["success"] is True
    assert result["allowed"] is True

    print("\nTEST 2 — BUYER SESSION BLOCK\n")

    result = service.validate_execution(
        execution_plan=execution_plan,
        user_memory={
            "buyer_session_active": True,
        },
    )

    print(result)

    assert result["success"] is False
    assert result["reason"] == "buyer_session_active"

    print("\nTEST 3 — AUTOMATION DISABLED\n")

    result = service.validate_execution(
        execution_plan=execution_plan,
        system_config={
            "ENABLE_POST_PURCHASE_AUTOMATION": False,
        },
    )

    print(result)

    assert result["success"] is False
    assert (
        result["reason"]
        == "post_purchase_automation_disabled"
    )

    print("\nTEST 4 — COOLDOWN ACTIVE\n")

    cooldown_until = service.build_cooldown_expiration(
        minutes=30
    )

    result = service.validate_execution(
        execution_plan=execution_plan,
        user_memory={
            "reaction_cooldown_until": cooldown_until,
        },
    )

    print(result)

    assert result["success"] is False
    assert result["reason"] == "reaction_cooldown_active"

    print("\nTEST 5 — RECENT REACTION\n")

    result = service.validate_execution(
        execution_plan=execution_plan,
        user_memory={
            "recent_reaction_sent": True,
        },
    )

    print(result)

    assert result["success"] is False
    assert (
        result["reason"]
        == "recent_reaction_already_sent"
    )

    print("\n✅ 3D.13.2 PASSED")


if __name__ == "__main__":
    run_test()
from app.services.reaction_buyer_session_protection_service import (
    ReactionBuyerSessionProtectionService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.5 BUYER SESSION PROTECTION")
    print("======================================\n")

    service = (
        ReactionBuyerSessionProtectionService()
    )

    execution_plan = {
        "fanvue_user_id": "fan_123",
        "decision_type": "thank_you_only",
    }

    print("TEST 1 — NO ACTIVE SESSION\n")

    result = service.validate_session_safety(
        execution_plan=execution_plan,
        user_memory={
            "buyer_session_active": False,
        },
    )

    print(result)

    assert result["success"] is True
    assert result["safe_to_execute"] is True

    print("\nTEST 2 — BLOCKED CONVERSATION MODE\n")

    result = service.validate_session_safety(
        execution_plan=execution_plan,
        user_memory={
            "buyer_session_active": True,
        },
        runtime_state={
            "conversation_mode": "close_mode",
        },
    )

    print(result)

    assert result["success"] is False
    assert (
        result["reason"]
        == "protected_conversation_mode"
    )

    print("\nTEST 3 — CLOSE FLOW ACTIVE\n")

    result = service.validate_session_safety(
        execution_plan=execution_plan,
        user_memory={
            "buyer_session_active": True,
        },
        runtime_state={
            "close_ready": True,
        },
    )

    print(result)

    assert result["success"] is False
    assert (
        result["reason"]
        == "close_flow_active"
    )

    print("\nTEST 4 — ESCALATION ACTIVE\n")

    result = service.validate_session_safety(
        execution_plan=execution_plan,
        user_memory={
            "buyer_session_active": True,
        },
        runtime_state={
            "escalation_active": True,
        },
    )

    print(result)

    assert result["success"] is False
    assert (
        result["reason"]
        == "runtime_escalation_active"
    )

    print("\nTEST 5 — SAFE ACTIVE SESSION\n")

    result = service.validate_session_safety(
        execution_plan=execution_plan,
        user_memory={
            "buyer_session_active": True,
        },
        runtime_state={
            "conversation_mode": "casual",
            "close_ready": False,
            "escalation_active": False,
        },
    )

    print(result)

    assert result["success"] is True
    assert result["safe_to_execute"] is True

    print("\n✅ 3D.13.5 PASSED")


if __name__ == "__main__":
    run_test()
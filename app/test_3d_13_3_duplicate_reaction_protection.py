from app.services.reaction_duplicate_guard_service import (
    ReactionDuplicateGuardService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.3 DUPLICATE REACTION PROTECTION")
    print("======================================\n")

    service = ReactionDuplicateGuardService()

    execution_plan = {
        "fanvue_user_id": "fan_123",
        "event_type": "purchase_received",
        "action_type": "send_thank_you_message",
        "raw_event": {
            "external_event_id": "evt_abc_123",
        },
    }

    print("TEST 1 — NO DUPLICATE\n")

    result = service.validate_duplicate_safety(
        execution_plan=execution_plan,
        reaction_history=[],
    )

    print(result)

    assert result["success"] is True
    assert result["duplicate"] is False

    print("\nTEST 2 — DUPLICATE EXTERNAL EVENT\n")

    result = service.validate_duplicate_safety(
        execution_plan=execution_plan,
        reaction_history=[
            {
                "external_event_id": "evt_abc_123",
                "fanvue_user_id": "fan_123",
                "event_type": "purchase_received",
                "action_type": "send_thank_you_message",
            }
        ],
    )

    print(result)

    assert result["success"] is False
    assert result["reason"] == "duplicate_external_event_reaction"

    print("\nTEST 3 — DUPLICATE USER/ACTION/EVENT\n")

    result = service.validate_duplicate_safety(
        execution_plan={
            "fanvue_user_id": "fan_123",
            "event_type": "tip_received",
            "action_type": "send_tip_reward_message",
            "raw_event": {},
        },
        reaction_history=[
            {
                "fanvue_user_id": "fan_123",
                "event_type": "tip_received",
                "action_type": "send_tip_reward_message",
            }
        ],
    )

    print(result)

    assert result["success"] is False
    assert result["reason"] == "duplicate_user_action_event_reaction"

    print("\nTEST 4 — MISSING ACTION TYPE\n")

    result = service.validate_duplicate_safety(
        execution_plan={
            "fanvue_user_id": "fan_123",
            "event_type": "purchase_received",
        },
    )

    print(result)

    assert result["success"] is False
    assert result["reason"] == "missing_action_type"

    print("\n✅ 3D.13.3 PASSED")


if __name__ == "__main__":
    run_test()
from app.services.automated_reaction_target_safety_service import (
    AutomatedReactionTargetSafetyService,
)


def main():
    service = AutomatedReactionTargetSafetyService()

    print("\n=== 3D.18.3 REACTION TARGET SAFETY TEST ===\n")

    valid_result = service.validate_target_safety(
        monetization_event={
            "event_type": "purchase_received",
            "local_user_id": 123,
            "fanvue_user_id": "fanvue_user_abc",
            "fanvue_account_id": "fanvue_account_abc",
            "fanvue_thread_id": "thread_123",
        }
    )

    print("valid target")
    print(valid_result)
    assert valid_result["success"] is True
    assert valid_result["blocked"] is False
    assert valid_result["target_safe"] is True
    assert valid_result["thread_context"]["value"] == "thread_123"
    print("PASS\n")

    missing_local_user_result = service.validate_target_safety(
        monetization_event={
            "event_type": "purchase_received",
            "fanvue_user_id": "fanvue_user_abc",
            "fanvue_account_id": "fanvue_account_abc",
            "fanvue_thread_id": "thread_123",
        }
    )

    print("missing local user mapping")
    print(missing_local_user_result)
    assert missing_local_user_result["success"] is False
    assert missing_local_user_result["blocked"] is True
    assert (
        missing_local_user_result["reason"]
        == "missing_local_user_mapping"
    )
    print("PASS\n")

    missing_thread_result = service.validate_target_safety(
        monetization_event={
            "event_type": "purchase_received",
            "local_user_id": 123,
            "fanvue_user_id": "fanvue_user_abc",
            "fanvue_account_id": "fanvue_account_abc",
        }
    )

    print("missing thread context")
    print(missing_thread_result)
    assert missing_thread_result["success"] is False
    assert missing_thread_result["blocked"] is True
    assert (
        missing_thread_result["reason"]
        == "missing_reaction_thread_context"
    )
    print("PASS\n")

    runtime_thread_result = service.validate_target_safety(
        monetization_event={
            "event_type": "purchase_received",
            "local_user_id": 123,
            "fanvue_user_id": "fanvue_user_abc",
            "fanvue_account_id": "fanvue_account_abc",
        },
        runtime_state={
            "fanvue_thread_id": "runtime_thread_456",
        },
    )

    print("thread from runtime_state")
    print(runtime_thread_result)
    assert runtime_thread_result["success"] is True
    assert runtime_thread_result["blocked"] is False
    assert (
        runtime_thread_result["thread_context"]["source"]
        == "runtime_state"
    )
    print("PASS\n")

    print("✅ 3D.18.3 Reaction Target Safety passed")


if __name__ == "__main__":
    main()
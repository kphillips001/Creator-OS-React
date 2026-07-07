from app.services.reaction_execution_service import (
    ReactionExecutionService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.1 REACTION EXECUTION FOUNDATION")
    print("======================================\n")

    service = ReactionExecutionService()

    monetization_event = {
        "event_type": "purchase_received",
        "fanvue_user_id": "fan_123",
        "fanvue_account_id": "acct_456",
        "amount": 29.99,
    }

    decision = {
        "decision": "thank_you_only",
        "aggression_level": "low",
        "pacing_profile": "decompression",
        "ppv_suppressed": True,
        "escalation_paused": True,
        "reasons": ["recent_purchase", "cooldown_active"],
    }

    result = service.build_execution_plan(
        monetization_event=monetization_event,
        post_purchase_decision=decision,
    )

    print(result)

    assert result["success"] is True
    assert result["blocked"] is False
    assert result["executed"] is False
    assert result["execution_mode"] == "plan_only"
    assert result["action_type"] == "send_thank_you_message"
    assert result["should_send_message"] is True
    assert result["should_queue_followup"] is False
    assert result["message_intent"] == "purchase_thank_you"

    premium_decision = {
        "decision": "premium_followup",
        "followup_mode": "delayed",
        "next_best_offer": "premium_followup_offer",
        "aggression_level": "medium",
        "pacing_profile": "premium",
        "reasons": ["active_buyer", "premium_eligible"],
    }

    premium_result = service.build_execution_plan(
        monetization_event=monetization_event,
        post_purchase_decision=premium_decision,
    )

    print(premium_result)

    assert premium_result["success"] is True
    assert premium_result["action_type"] == "queue_premium_followup"
    assert premium_result["should_send_message"] is False
    assert premium_result["should_queue_followup"] is True

    missing_user_result = service.build_execution_plan(
        monetization_event={
            "event_type": "tip_received",
        },
        post_purchase_decision={
            "decision": "tip_reward",
        },
    )

    print(missing_user_result)

    assert missing_user_result["success"] is False
    assert missing_user_result["blocked"] is True
    assert missing_user_result["reason"] == "missing_fanvue_user_id"

    print("\n✅ 3D.13.1 PASSED")


if __name__ == "__main__":
    run_test()
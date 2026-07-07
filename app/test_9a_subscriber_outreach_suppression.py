from app.services.outreach_service import OutreachService


def run_test():
    outreach_service = OutreachService()

    test_users = [
        {
            "name": "TEST A - Active subscriber should be blocked",
            "memory": {
                "fanvue_user_id": 101,
                "username": "active_sub_test",
                "is_subscriber": True,
                "relationship_status": "subscriber",
                "subscriber_profile": "ACTIVE_SUBSCRIBER",
                "outreach_status": "eligible",
            },
            "expected": False,
            "expected_reason": "subscriber_detected",
        },
        {
            "name": "TEST B - High-value subscriber should be blocked",
            "memory": {
                "fanvue_user_id": 102,
                "username": "high_value_sub_test",
                "is_subscriber": False,
                "relationship_status": "subscriber",
                "subscriber_profile": "HIGH_VALUE_SUBSCRIBER",
                "outreach_status": "eligible",
            },
            "expected": False,
            "expected_reason": "subscriber_detected",
        },
        {
            "name": "TEST C - Normal follower should be allowed",
            "memory": {
                "fanvue_user_id": 103,
                "username": "normal_follower_test",
                "is_subscriber": False,
                "relationship_status": "follower",
                "subscriber_profile": "",
                "outreach_status": "eligible",
                "offer_state": "none",
                "post_offer_nudge_count": 0,
                "outreach_attempts": 0,
                "last_outreach_at": None,
                "last_inbound_at": None,
                "is_whale": False,
            },
            "expected": True,
            "expected_reason": "User is eligible for outreach.",
        },
    ]

    print("\n========================================")
    print("9A TEST — Subscriber Outreach Suppression")
    print("========================================\n")

    for test in test_users:
        eligible, reason = outreach_service.is_user_eligible_for_outreach(test["memory"])

        passed = (
            eligible == test["expected"]
            and reason == test["expected_reason"]
        )

        print(test["name"])
        print(f"Eligible: {eligible}")
        print(f"Reason: {reason}")
        print(f"Expected Eligible: {test['expected']}")
        print(f"Expected Reason: {test['expected_reason']}")
        print("RESULT:", "✅ PASS" if passed else "❌ FAIL")
        print("----------------------------------------")


if __name__ == "__main__":
    run_test()
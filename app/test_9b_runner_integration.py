from app.services.outreach_runner import OutreachRunner


def run_test():
    runner = OutreachRunner()

    test_users = [
        {
            "name": "TEST A - Subscriber should use contextual outreach",
            "memory": {
                "fanvue_user_id": 301,
                "username": "subscriber_user",
                "is_subscriber": True,
                "relationship_status": "subscriber",
                "subscriber_profile": "ACTIVE_SUBSCRIBER",
                "subscriber_rewarm_required": False,
                "offer_state": "none",
                "post_offer_nudge_count": 0,
                "last_nudge_timestamp": None,
                "last_inbound_at": None,
                "last_outreach_at": None,
                "is_whale": False,
            },
            "expected_mode": "subscriber_contextual",
        },
        {
            "name": "TEST B - Follower should use standard outreach",
            "memory": {
                "fanvue_user_id": 302,
                "username": "follower_user",
                "is_subscriber": False,
                "relationship_status": "follower",
                "subscriber_profile": "",
                "outreach_status": "eligible",
                "offer_state": "none",
                "post_offer_nudge_count": 0,
                "last_outreach_at": None,
                "last_inbound_at": None,
                "is_whale": False,
            },
            "expected_mode": "standard",
        },
        {
            "name": "TEST C - Subscriber in rewarm should NOT be eligible",
            "memory": {
                "fanvue_user_id": 303,
                "username": "rewarm_user",
                "is_subscriber": True,
                "relationship_status": "subscriber",
                "subscriber_profile": "LAPSED_SUBSCRIBER",
                "subscriber_rewarm_required": True,
            },
            "expected_mode": None,
        },
    ]

    print("\n========================================")
    print("9B TEST — Runner Integration")
    print("========================================\n")

    for test in test_users:
        # Directly call internal logic without DB
        result = runner.outreach_service.is_user_eligible_for_subscriber_contextual_outreach(
            test["memory"]
        )

        subscriber_eligible, _ = result

        if subscriber_eligible:
            mode = "subscriber_contextual"
        else:
            preview = runner.outreach_service.build_outreach_preview(test["memory"])
            if preview["eligible"]:
                mode = "standard"
            else:
                mode = None

        passed = mode == test["expected_mode"]

        print(test["name"])
        print(f"Detected Mode: {mode}")
        print(f"Expected Mode: {test['expected_mode']}")
        print("RESULT:", "✅ PASS" if passed else "❌ FAIL")
        print("----------------------------------------")


if __name__ == "__main__":
    run_test()
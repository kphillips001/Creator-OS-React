from app.services.outreach_service import OutreachService


def run_test():
    service = OutreachService()

    test_users = [
        {
            "name": "TEST A - Cold user with first response upgrades to low",
            "memory": {
                "user_value_tier": "cold",
                "inbound_message_count": 1,
                "outreach_response_count": 0,
            },
            "expected_tier": "low",
        },
        {
            "name": "TEST B - Low user with repeat engagement upgrades to medium",
            "memory": {
                "user_value_tier": "low",
                "inbound_message_count": 3,
                "outreach_response_count": 0,
            },
            "expected_tier": "medium",
        },
        {
            "name": "TEST C - Medium user with strong engagement upgrades to high",
            "memory": {
                "user_value_tier": "medium",
                "inbound_message_count": 6,
                "outreach_response_count": 0,
            },
            "expected_tier": "high",
        },
        {
            "name": "TEST D - High user does not upgrade",
            "memory": {
                "user_value_tier": "high",
                "inbound_message_count": 10,
                "outreach_response_count": 5,
            },
            "expected_tier": None,
        },
        {
            "name": "TEST E - Cold inactive user does not upgrade",
            "memory": {
                "user_value_tier": "cold",
                "inbound_message_count": 0,
                "outreach_response_count": 0,
            },
            "expected_tier": None,
        },
    ]

    print("\n========================================")
    print("9D TEST — Engagement-Based Value Tier Upgrade")
    print("========================================\n")

    for test in test_users:
        new_tier, reasons = service.evaluate_user_value_upgrade(test["memory"])

        passed = new_tier == test["expected_tier"]

        print(test["name"])
        print(f"New Tier: {new_tier}")
        print(f"Reasons: {reasons}")
        print(f"Expected Tier: {test['expected_tier']}")
        print("RESULT:", "✅ PASS" if passed else "❌ FAIL")
        print("----------------------------------------")


if __name__ == "__main__":
    run_test()
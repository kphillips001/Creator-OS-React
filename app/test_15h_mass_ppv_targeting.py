from app.services.mass_ppv_targeting_service import MassPPVTargetingService


def run_test():
    service = MassPPVTargetingService()

    test_users = [
        {
            "label": "Follower",
            "fanvue_user": {"id": 1, "username": "follower"},
            "memory": {
                "is_subscriber": False,
                "user_value_tier": "cold",
            },
        },
        {
            "label": "Low Value Subscriber",
            "fanvue_user": {"id": 2, "username": "low_sub"},
            "memory": {
                "is_subscriber": True,
                "subscriber_profile": "ACTIVE_SUBSCRIBER",
                "intent_score": 10,
                "user_value_tier": "low",
            },
        },
        {
            "label": "High Value Subscriber",
            "fanvue_user": {"id": 3, "username": "high_sub"},
            "memory": {
                "is_subscriber": True,
                "subscriber_profile": "HIGH_VALUE_SUBSCRIBER",
                "intent_score": 90,
                "user_value_tier": "high",
            },
        },
        {
            "label": "Rewarm User",
            "fanvue_user": {"id": 4, "username": "rewarm"},
            "memory": {
                "is_subscriber": True,
                "subscriber_rewarm_required": True,
                "user_value_tier": "low",
            },
        },
    ]

    for test in test_users:
        print(f"\n=== TEST: {test['label']} ===")

        eligible, reason = service.is_user_eligible_for_mass_ppv(
            fanvue_user=test["fanvue_user"],
            memory=test["memory"],
        )

        print(f"eligible={eligible} reason={reason}")


if __name__ == "__main__":
    run_test()
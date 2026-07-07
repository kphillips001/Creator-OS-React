from app.services.mass_ppv_targeting_service import MassPPVTargetingService


def run_test():
    service = MassPPVTargetingService()

    test_cases = [
        {
            "name": "Follower should be eligible",
            "fanvue_user": {
                "id": 1,
                "username": "follower_user",
                "relationship_status": "follower",
                "is_subscriber": False,
            },
            "memory": {
                "user_value_tier": "low",
                "buyer_tier": "low",
            },
        },
        {
            "name": "Whale should be blocked",
            "fanvue_user": {
                "id": 2,
                "username": "whale_user",
                "relationship_status": "subscriber",
                "is_subscriber": True,
            },
            "memory": {
                "is_whale": True,
                "user_value_tier": "whale",
            },
        },
        {
            "name": "High value user should be blocked",
            "fanvue_user": {
                "id": 3,
                "username": "high_value_user",
                "relationship_status": "subscriber",
                "is_subscriber": True,
            },
            "memory": {
                "user_value_tier": "high",
            },
        },
        {
            "name": "Low value subscriber should be eligible",
            "fanvue_user": {
                "id": 4,
                "username": "low_subscriber",
                "relationship_status": "subscriber",
                "is_subscriber": True,
            },
            "memory": {
                "user_value_tier": "low",
                "buyer_tier": "low",
            },
        },
        {
            "name": "Active buyer session should be blocked",
            "fanvue_user": {
                "id": 5,
                "username": "active_buyer",
                "relationship_status": "follower",
                "is_subscriber": False,
            },
            "memory": {
                "buyer_session_active": True,
                "user_value_tier": "low",
            },
        },
        {
            "name": "One-on-one monetization should be blocked",
            "fanvue_user": {
                "id": 6,
                "username": "one_on_one_user",
                "relationship_status": "follower",
                "is_subscriber": False,
            },
            "memory": {
                "current_route": "sales",
                "recommended_action": "build_tension",
                "user_value_tier": "low",
            },
        },
    ]

    print("\n==============================")
    print("MASS PPV TARGETING TEST")
    print("==============================")

    for case in test_cases:
        print(f"\n--- {case['name']} ---")

        eligible, reason = service.is_user_eligible_for_mass_ppv(
            fanvue_user=case["fanvue_user"],
            memory=case["memory"],
        )

        print(f"eligible={eligible}")
        print(f"reason={reason}")

    print("\n✅ Mass PPV targeting test complete")


if __name__ == "__main__":
    run_test()
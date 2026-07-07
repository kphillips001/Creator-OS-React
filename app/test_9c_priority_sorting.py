from app.services.outreach_runner import OutreachRunner


def run_test():
    runner = OutreachRunner()

    test_users = [
        {
            "fanvue_user_id": 401,
            "username": "fresh_cold_follower",
            "user_type": "follower",
            "relationship_status": "follower",
            "user_value_tier": "cold",
            "outreach_attempts": 0,
            "outreach_ignore_count": 0,
        },
        {
            "fanvue_user_id": 402,
            "username": "ignored_once",
            "user_type": "follower",
            "relationship_status": "follower",
            "user_value_tier": "low",
            "outreach_attempts": 1,
            "outreach_ignore_count": 1,
        },
        {
            "fanvue_user_id": 403,
            "username": "ignored_many",
            "user_type": "follower",
            "relationship_status": "follower",
            "user_value_tier": "low",
            "outreach_attempts": 3,
            "outreach_ignore_count": 3,
        },
        {
            "fanvue_user_id": 404,
            "username": "previous_responder",
            "user_type": "follower",
            "relationship_status": "follower",
            "user_value_tier": "low",
            "outreach_response_count": 2,
        },
        {
            "fanvue_user_id": 405,
            "username": "recently_active",
            "user_type": "follower",
            "relationship_status": "follower",
            "user_value_tier": "low",
            "last_inbound_at": None,  # will override below
        },
    ]

    # Force "recent activity" on last user
    from datetime import datetime
    test_users[4]["last_inbound_at"] = datetime.utcnow()

    print("\n========================================")
    print("9C TEST — Priority Scoring + Sorting")
    print("========================================\n")

    scored_users = []

    for user in test_users:
        score, reasons = runner.outreach_service.calculate_outreach_priority_score(user)

        scored_users.append({
            **user,
            "score": score,
            "reasons": reasons,
        })

    # Sort same way as production
    scored_users.sort(key=lambda u: u["score"], reverse=True)

    print("FINAL ORDER (Highest Priority → Lowest):\n")

    for user in scored_users:
        print(
            f"user={user['fanvue_user_id']} | "
            f"{user['username']} | "
            f"score={user['score']} | "
            f"reasons={user['reasons']}"
        )

    print("\n----------------------------------------")
    print("EXPECTED BEHAVIOR:\n")
    print("1. fresh_cold_follower → TOP")
    print("2. ignored_once → HIGH")
    print("3. previous_responder → LOWER")
    print("4. recently_active → LOWER")
    print("5. ignored_many → BOTTOM")
    print("----------------------------------------")


if __name__ == "__main__":
    run_test()
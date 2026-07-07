from datetime import datetime, timedelta, timezone

from app.services.outreach_service import OutreachService


def run_test():
    service = OutreachService(
        outreach_cooldown_hours=6,
        recent_activity_hours=24,
        max_outreach_attempts=3,
    )

    now = datetime.now(timezone.utc)

    test_users = [
        {
            "name": "TEST A - Fresh follower eligible",
            "memory": {
                "fanvue_user_id": 601,
                "username": "fresh_follower",
                "user_type": "follower",
                "relationship_status": "follower",
                "outreach_status": "eligible",
                "outreach_attempts": 0,
                "outreach_ignore_count": 0,
                "last_outreach_at": None,
                "last_inbound_at": None,
                "offer_state": "none",
                "post_offer_nudge_count": 0,
                "is_subscriber": False,
                "is_whale": False,
            },
            "expected": True,
        },
        {
            "name": "TEST B - Attempt 1 inside adaptive cooldown blocked",
            "memory": {
                "fanvue_user_id": 602,
                "username": "cooldown_attempt_1",
                "user_type": "follower",
                "relationship_status": "follower",
                "outreach_status": "eligible",
                "outreach_attempts": 1,
                "outreach_ignore_count": 1,
                "last_outreach_at": now - timedelta(hours=8),
                "last_inbound_at": None,
                "offer_state": "none",
                "post_offer_nudge_count": 0,
                "is_subscriber": False,
                "is_whale": False,
            },
            "expected": False,
        },
        {
            "name": "TEST C - Attempt 2 inside adaptive cooldown blocked",
            "memory": {
                "fanvue_user_id": 603,
                "username": "cooldown_attempt_2",
                "user_type": "follower",
                "relationship_status": "follower",
                "outreach_status": "eligible",
                "outreach_attempts": 2,
                "outreach_ignore_count": 2,
                "last_outreach_at": now - timedelta(hours=20),
                "last_inbound_at": None,
                "offer_state": "none",
                "post_offer_nudge_count": 0,
                "is_subscriber": False,
                "is_whale": False,
            },
            "expected": False,
        },
        {
            "name": "TEST D - Max attempts exhausted blocked",
            "memory": {
                "fanvue_user_id": 604,
                "username": "exhausted_user",
                "user_type": "follower",
                "relationship_status": "follower",
                "outreach_status": "eligible",
                "outreach_attempts": 3,
                "outreach_ignore_count": 3,
                "last_outreach_at": now - timedelta(hours=72),
                "last_inbound_at": None,
                "offer_state": "none",
                "post_offer_nudge_count": 0,
                "is_subscriber": False,
                "is_whale": False,
            },
            "expected": False,
        },
        {
            "name": "TEST E - Engaged user blocked from cold outreach",
            "memory": {
                "fanvue_user_id": 605,
                "username": "engaged_user",
                "user_type": "follower",
                "relationship_status": "follower",
                "outreach_status": "engaged",
                "outreach_attempts": 1,
                "outreach_ignore_count": 0,
                "last_outreach_at": None,
                "last_inbound_at": None,
                "offer_state": "none",
                "post_offer_nudge_count": 0,
                "is_subscriber": False,
                "is_whale": False,
            },
            "expected": False,
        },
    ]

    print("\n========================================")
    print("9F TEST — Outreach Cooldown + Anti-Spam")
    print("========================================\n")

    for test in test_users:
        eligible, reason = service.is_user_eligible_for_outreach(test["memory"])
        passed = eligible == test["expected"]

        print(test["name"])
        print(f"Eligible: {eligible}")
        print(f"Reason: {reason}")
        print(f"Expected Eligible: {test['expected']}")
        print("RESULT:", "✅ PASS" if passed else "❌ FAIL")
        print("----------------------------------------")


if __name__ == "__main__":
    run_test()
from app.services.outreach_service import OutreachService
from datetime import datetime

def run_test():
    outreach_service = OutreachService()

    test_users = [
        {
            "name": "TEST A - Active subscriber should be eligible",
            "memory": {
                "fanvue_user_id": 201,
                "username": "active_sub",
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
            "expected": True,
            "expected_reason": "subscriber_contextual_outreach_eligible",
        },
        {
            "name": "TEST B - Subscriber in rewarm should be blocked",
            "memory": {
                "fanvue_user_id": 202,
                "username": "rewarm_sub",
                "is_subscriber": True,
                "relationship_status": "subscriber",
                "subscriber_profile": "LAPSED_SUBSCRIBER",
                "subscriber_rewarm_required": True,
            },
            "expected": False,
            "expected_reason": "subscriber_rewarm_required",
        },
        {
            "name": "TEST C - Subscriber in active offer should be blocked",
            "memory": {
                "fanvue_user_id": 203,
                "username": "offer_sub",
                "is_subscriber": True,
                "relationship_status": "subscriber",
                "subscriber_profile": "ACTIVE_SUBSCRIBER",
                "subscriber_rewarm_required": False,
                "offer_state": "offered",
            },
            "expected": False,
            "expected_reason": "active_offer_flow:offered",
        },
        {
            "name": "TEST D - Recently active subscriber should be blocked",
            "memory": {
                "fanvue_user_id": 204,
                "username": "recent_sub",
                "is_subscriber": True,
                "relationship_status": "subscriber",
                "subscriber_profile": "ACTIVE_SUBSCRIBER",
                "subscriber_rewarm_required": False,
                "last_inbound_at": datetime.utcnow(),
            },
            "expected": False,
            "expected_reason": "subscriber_recently_active",
        },
        {
            "name": "TEST E - Non-subscriber should be blocked",
            "memory": {
                "fanvue_user_id": 205,
                "username": "follower_user",
                "is_subscriber": False,
                "relationship_status": "follower",
                "subscriber_profile": "",
            },
            "expected": False,
            "expected_reason": "not_subscriber",
        },
    ]

    print("\n========================================")
    print("9B TEST — Subscriber Contextual Outreach")
    print("========================================\n")

    for test in test_users:
        eligible, reason = outreach_service.is_user_eligible_for_subscriber_contextual_outreach(
            test["memory"]
        )

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